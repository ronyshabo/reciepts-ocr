document.addEventListener('DOMContentLoaded', function() {
    const uploadForm = document.getElementById('upload-form');
    const resultContainer = document.getElementById('result-container');

    uploadForm.addEventListener('submit', function(event) {
        event.preventDefault();
        
        const formData = new FormData(uploadForm);
        
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                resultContainer.innerHTML = `<h3>Processed Receipt:</h3><pre>${JSON.stringify(data.result, null, 2)}</pre>`;
            } else {
                resultContainer.innerHTML = `<h3>Error:</h3><p>${data.error}</p>`;
            }
        })
        .catch(error => {
            resultContainer.innerHTML = `<h3>Error:</h3><p>${error.message}</p>`;
        });
    });
});