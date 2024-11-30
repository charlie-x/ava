import os
import sys
import threading
from threading import Lock
import flask
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import numpy as np
import tempfile
import subprocess
import azure.cognitiveservices.speech as speechsdk
import whisper
import torch

from openai import OpenAI


from better_profanity import profanity  

# initialize profanity filter with the default word list
profanity.load_censor_words()

# initialize Flask app and SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'fdsfdsfdsf34543543dfgdfghfd%$#%#$%$#%#$'
socketio = SocketIO(app)

# initialize threading lock for thread safety
user_conversations_lock = Lock()

# dictionary to store per-user conversation histories
user_conversations = {}

# set your OpenAI API key using the CHAT_GPT_API_KEY environment variable
api_key = os.getenv('CHAT_GPT_API_KEY')
if not api_key:
    print("Error: The OpenAI API key is not set. Please set the CHAT_GPT_API_KEY environment variable.")
    sys.exit(1)

client = OpenAI(api_key=api_key)

# azure speech service key and region from environment variables
azure_speech_key = os.getenv('AZURE_SPEECH_KEY')
azure_service_region = os.getenv('AZURE_SERVICE_REGION')
if not azure_speech_key or not azure_service_region:
    print("Error: Azure Speech service key and region must be set in environment variables.")
    sys.exit(1)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Using device: {device}")
whisper_model = whisper.load_model('base', device=device)  # You can choose other models

speech_config = speechsdk.SpeechConfig(subscription=azure_speech_key, region=azure_service_region)

# set the voice to Ava neural
speech_config.speech_synthesis_voice_name = 'en-US-AvaNeural'

@app.route('/')
def index():
    return render_template('index.html')

def get_user_conversation():
    sid = request.sid
    with user_conversations_lock:
        if sid not in user_conversations:
            user_conversations[sid] = [
                {
                    "role": "system",
                    "content": (
                        "You are an AI assistant called Ava that provides helpful and informative responses that are designed fora text to speech process so don't use sterisks etc, "
                        "keep it brief and friendly, a little sassy, "
                        "sarcastic, and playful and don't "
                        "let anyone know you are an AI or computer."
                        "Don't use emoticons or emojis that can't be used in text to speech conversions."
                    )
                }
            ]
    return user_conversations[sid]

@socketio.on('audio_data')
def handle_audio_data(data):
    sid = request.sid
    print(f"Received audio data from client {sid}.")
    conversation = get_user_conversation()
    audio_bytes = data['audio_data']

    with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_audio_file:
        temp_filename = temp_audio_file.name
        temp_audio_file.write(audio_bytes)

    temp_wav_file = temp_filename + '.wav'
    result = subprocess.run(['ffmpeg', '-y', '-i', temp_filename, temp_wav_file], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg error: {result.stderr}")
        emit('error', {'error': "Audio conversion failed."}, room=sid)
        os.unlink(temp_filename)
        return

    try:
        # transcribe audio
        user_input = transcribe_audio(temp_wav_file)
        if user_input.strip():
            
            # censor user input, coz this goes real bad otherwise
            censored_input = censor_text(user_input)
            print(f"Censored user input: {censored_input}")

            response = generate_response(censored_input, conversation)

            audio_response = synthesize_speech(response)
            if audio_response:
                
                # send the response back to the client, including user's original transcribed text
                emit('audio_response', {
                    'user_text': user_input,
                    'assistant_text': response,
                    'audio_data': audio_response
                }, room=sid)
            else:
                emit('error', {'error': "Error during speech synthesis."}, room=sid)
        else:
            emit('error', {'error': "I didn't catch that. Could you please repeat?"}, room=sid)
    except Exception as e:
        print(f"An error occurred: {e}")
        emit('error', {'error': "An error occurred during processing."}, room=sid)
    finally:

        os.unlink(temp_filename)
        os.unlink(temp_wav_file)
        print(f"Temporary files deleted for client {sid}.")

def transcribe_audio(filename):
    print("Transcribing...")
    try:
        result = whisper_model.transcribe(filename)
        text = result['text'].strip()
        print(f"User said: {text}")
        return text
    except Exception as e:
        print(f"Error transcribing audio: {e}")
        return ""

def generate_response(user_input, conversation):
    print("Generating response...")
    try:
        # append user's input to the conversation history
        conversation.append({"role": "user", "content": user_input})
        
        # send the conversation history to the API
        response = client.chat.completions.create(model="gpt-4o-mini",
        messages=conversation)

        reply = response.choices[0].message.content.strip()
        print(f"Assistant: {reply}")
        # append assistant's reply to the conversation history
        conversation.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        print(f"Error communicating with OpenAI API: {e}")
        return "I'm having trouble connecting to the server."

def synthesize_speech(text):
    print(f"Synthesizing speech for text: {text}")
    try:
        # create a speech synthesizer without audio output (we don't want to play the audio on the server)
        speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

        # start the speech synthesis
        result = speech_synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print("Speech synthesized successfully.")
            
            # get the audio data from the result
            audio_data = result.audio_data  # This is a bytes object containing the audio data
            return audio_data
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print(f"Speech synthesis canceled: {cancellation_details.reason}")
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                print(f"Error details: {cancellation_details.error_details}")
            return None
    except Exception as e:
        print(f"Error during speech synthesis: {e}")
        return None

def censor_text(text):
    """
    Censors profane words in the text using better_profanity library.

    Args:
        text (str): The text to censor.

    Returns:
        str: The censored text.
    """
    censored_text = profanity.censor(text)
    return censored_text

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    with user_conversations_lock:
        if sid in user_conversations:
            del user_conversations[sid]
            print(f"Deleted conversation for session {sid}.")

if __name__ == "__main__":
    print("Starting Flask app with HTTPS...")
    socketio.run(app, host='0.0.0.0', port=5000, certfile='cert.pem', keyfile='key.pem')