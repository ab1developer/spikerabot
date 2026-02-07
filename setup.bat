@echo off
echo Installing spikerabot dependencies...

echo.
echo Step 1: Installing Python packages...
pip install -r requirements.txt

echo.
echo Step 2: Downloading spaCy Russian model...
python -m spacy download ru_core_news_sm

echo.
echo Step 3: Verifying installation...
python -c "import llama_index; print('LlamaIndex:', llama_index.__version__)"
python -c "import spacy; nlp = spacy.load('ru_core_news_sm'); print('spaCy Russian model: OK')"
python -c "import sentence_transformers; print('SentenceTransformers: OK')"
python -c "import telebot; print('pyTelegramBotAPI: OK')"
python -c "import ollama; print('Ollama client: OK')"

echo.
echo Setup complete! Make sure you have Ollama running locally.
echo You can start it with: ollama serve
pause