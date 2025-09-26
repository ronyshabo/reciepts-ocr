# Receipt Processor App

This is a Flask web application designed to process receipts by allowing users to upload images or PDF files. The application utilizes the OpenAI API to extract information from the receipts and saves the results in a Firebase collection.

## Features

- Upload receipt images or PDF files.
- Process receipts using the OpenAI API.
- Store processed receipt data in Firebase.
- User-friendly interface for uploading and viewing results.

## Project Structure

```
receipt-processor-app
├── app.py                  # Entry point of the Flask application
├── requirements.txt        # Project dependencies
├── config.py               # Configuration settings for Firebase and OpenAI
├── templates               # HTML templates for the application
│   ├── index.html         # Main interface for uploading receipts
│   └── upload.html        # Upload form and results display
├── static                  # Static files (CSS and JS)
│   ├── css
│   │   └── style.css      # Styles for the application
│   └── js
│       └── main.js        # Client-side JavaScript functionality
├── services                # Services for interacting with APIs
│   ├── __init__.py        # Initializes the services package
│   ├── openai_service.py   # Functions for OpenAI API interaction
│   └── firebase_service.py  # Functions for Firebase interaction
├── models                  # Data models for the application
│   ├── __init__.py        # Initializes the models package
│   └── receipt.py         # Data model for receipts
├── utils                   # Utility functions
│   ├── __init__.py        # Initializes the utils package
│   └── file_handler.py     # Functions for file handling
├── uploads                 # Directory for temporarily storing uploaded files
└── README.md               # Documentation for the project
```

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd receipt-processor-app
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Configure your Firebase and OpenAI API keys in `config.py`.

## Usage

1. Run the Flask application:
   ```
   python app.py
   ```

2. Open your web browser and navigate to `http://127.0.0.1:5000`.

3. Use the interface to upload your receipt files and view the processed results.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## License

This project is licensed under the MIT License.