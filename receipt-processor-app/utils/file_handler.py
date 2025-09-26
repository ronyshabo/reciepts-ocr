def save_uploaded_file(file, upload_folder):
    import os
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        return file_path
    return None

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def delete_file(file_path):
    import os
    if os.path.exists(file_path):
        os.remove(file_path)