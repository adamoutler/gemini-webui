import io
from unittest.mock import patch
from src.fake_gemini import run_fake_gemini

def test_fake_gemini_logic():
    # Simulate user input
    input_data = (
        "Hello\n"
        "Remember this TEST_VALUE: 12345\n"
        "What is the TEST_VALUE?\n"
        "EXIT\n"
    )
    
    with patch('sys.stdin', io.StringIO(input_data)), \
         patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
        
        run_fake_gemini()
        
        output = mock_stdout.getvalue()
        assert "Welcome to Fake Gemini" in output
        assert "I will remember TEST_VALUE: 12345" in output
        assert "The TEST_VALUE is 12345" in output
        assert "You said: Hello" in output

def test_fake_gemini_missing_value():
    input_data = "What is the TEST_VALUE?\nEXIT\n"
    with patch('sys.stdin', io.StringIO(input_data)), \
         patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
        run_fake_gemini()
        assert "I don't know the TEST_VALUE." in mock_stdout.getvalue()
