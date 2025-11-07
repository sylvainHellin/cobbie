'''
Count the number of tokens of the provided text.
'''

import argparse
import sys
import os

# Add the parent directory to the path to import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import tiktoken
except ImportError:
    print("Error: tiktoken is not installed. Install it with: uv add tiktoken")
    sys.exit(1)


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """
    Count the number of tokens in the given text using tiktoken.

    Args:
        text: The text to count tokens for
        model: The model name to use for tokenization (default: gpt-3.5-turbo)

    Returns:
        The number of tokens in the text
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to a default encoding if the model is not found
        encoding = tiktoken.get_encoding("cl100k_base")

    return len(encoding.encode(text))


def main():
    parser = argparse.ArgumentParser(description="Count the number of tokens in text")
    parser.add_argument("text", nargs="?", help="The text to count tokens for (optional, reads from text_count_tokens.txt if not provided)")
    parser.add_argument(
        "--model",
        default="gpt-3.5-turbo",
        help="The model name to use for tokenization (default: gpt-3.5-turbo)"
    )

    args = parser.parse_args()

    if args.text:
        # Use the provided text argument
        text = args.text
        print("Counting tokens for provided text...")
    else:
        # Read from text_count_tokens.txt file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "text_count_tokens.txt")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            print(f"Counting tokens for text from {file_path}...")
        except FileNotFoundError:
            print(f"Error: {file_path} not found.")
            print("Either provide text as an argument or create text_count_tokens.txt in the same directory.")
            sys.exit(1)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            sys.exit(1)

    token_count = count_tokens(text, args.model)
    print(f"Token count: {token_count}")


if __name__ == "__main__":
    main()
