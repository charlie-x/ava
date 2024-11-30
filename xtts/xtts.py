from auralis import TTS, TTSRequest


# Initialize
tts = TTS().from_pretrained('AstraMindAI/xttsv2')

# Generate speech
request = TTSRequest(
    text="Hi this is AstraMind,  How can I help you today?",
    speaker_files=['female.wav'],
    temperature=0.75,
    repetition_penalty=6.5
)

output = tts.generate_speech(request)
output.save('hello.wav')