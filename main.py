import datetime
from flask import Flask, render_template, request,redirect, Response, flash
from google.cloud import datastore
from google.cloud import storage
import google.oauth2.id_token
from google.auth.transport import requests
import local_constants

app = Flask(__name__)

# get access to the datastore client so we can add and store data in the datastore
datastore_client = datastore.Client()
app.secret_key = b'%@LMq58:t|O#FAf' # Used for error messages through Flask Flash

# get access to a request adapter for firebase as we will need this to authenticate users
firebase_request_adapter = requests.Request()

"""
createUserInfo: Creates a User entity and adds it to the database.
"""
def createUserInfo(claims):
    entity_key = datastore_client.key('UserInfo', claims['email'])
    entity = datastore.Entity(key = entity_key)
    entity.update({
    'email': claims['email'],
    'current_directory': "/"
    })
    datastore_client.put(entity)
    addDirectory(claims['email'] + "/") #add user specific root directory

"""
retrieveUserInfo: Retrieves a user. Used to retrieve user's info who's logged in.
"""
def retrieveUserInfo(claims):
    entity_key = datastore_client.key('UserInfo', claims['email'])
    entity = datastore_client.get(entity_key)
    return entity

"""
changeCurrentDirectory: Changes the current directory of the provided user.
"""
def changeCurrentDirectory(user_email, new_directory):
    entity_key = datastore_client.key('UserInfo', user_email)
    entity = datastore.Entity(key = entity_key)
    entity.update({
        'email': user_email,
        'current_directory': new_directory
    })
    datastore_client.put(entity)

"""
blobList: Returns a list of blobs in the storage. If a prefix is provided,
          returns blobs under the prefix.
"""
def blobList(prefix):
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)
    return storage_client.list_blobs(local_constants.PROJECT_STORAGE_BUCKET,
    prefix=prefix)

"""
addDirectory: Uploads a new directory to the storage with the provided directory name.
"""
def addDirectory(directory_name):
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
    blob = bucket.blob(directory_name)
    blob.upload_from_string('', content_type='application/x-www-formurlencoded;charset=UTF-8')

"""
removeDirectory: Removes the directory from the storage with the provided directory name.
"""
def removeDirectory(directory_name):
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
    blob = bucket.blob(directory_name)
    blob.delete()

"""
addFile: Adds a new file to the specified directory.
"""
def addFile(directory, file):
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
    blob = bucket.blob(directory)
    blob.upload_from_file(file)
'''
removeFile: Removes the file at the provided file_path. Filename is included in the file path.
'''
def removeFile(file_path):
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
    blob = bucket.blob(file_path)
    blob.delete()

'''
downloadBlob: Downloads a file as bytes, provided the filename.
'''
def downloadBlob(filename):
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
    blob = bucket.blob(filename)
    return blob.download_as_bytes()

'''
shareFile: Uploads the provided file from this user's storage to shared user's
           ".sh/sharer_email/" directory.
'''
def shareFile(sharer_user_info, filename, sharee_email):
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
    blob = bucket.blob(sharer_user_info['email'] + sharer_user_info['current_directory'] + filename)
    blob.reload()
    with blob.open("rb") as f:
        addFile(sharee_email + "/" + ".sh/" + sharer_user_info['email'] + "/" + filename, f)


'''
checkDuplicateFilesICD: Checks the provided file against all files in current directory.
                        Compares their MD_5 hashes. Returns a list of files that have
                        the same hash as the provided file.
'''
def checkDuplicateFilesICD(user_info, filename):
    duplicate_files = []
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
    blob = bucket.blob(user_info['email'] + user_info['current_directory'] + filename)
    blob.reload()
    file_md5 = blob.md5_hash

    blob_list = blobList(user_info['email'] +  user_info['current_directory'])

    for i in blob_list:
        if i.name[len(i.name) - 1] != '/':
            if blob.name != i.name:
                if str(file_md5) == str(i.md5_hash):
                    i.name = i.name[len(user_info['email']) + len(user_info['current_directory']):]
                    if i.name[0:len(i.name)-1].find('/') == -1:
                        duplicate_files.append(i)
    return duplicate_files

'''
checkDuplicateFiles: Checks the provided file against all files in user's directory.
                     Compares their MD_5 hashes. Returns a list of files that have
                     the same hash as the provided file.
'''
def checkDuplicateFiles(user_info, filename):
    duplicate_files = []
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
    blob = bucket.blob(user_info['email'] + user_info['current_directory'] + filename)
    blob.reload()
    file_md5 = blob.md5_hash

    blob_list = blobList(user_info['email'] + "/")

    for i in blob_list:
        if i.name[len(i.name) - 1] != '/':
            if blob.name != i.name:
                if str(file_md5) == str(i.md5_hash):
                    i.name = i.name[len(user_info['email']):]
                    if i.name[0:len("/.sh/")] != "/.sh/": #Dont check shared folder
                        duplicate_files.append(i)
    return duplicate_files

'''
addDirectoryHandler: Handler to add a directory. Implements appropriate checks
                     for directory name, if its valid, calls addDirectory function
                     to add it to storage. Redirects to home page.
'''
@app.route('/add_directory', methods=['POST'])
def addDirectoryHandler():
    id_token = request.cookies.get("token")
    error_message = None
    claims = None
    if id_token:
        try:
            claims = google.oauth2.id_token.verify_firebase_token(id_token,
            firebase_request_adapter)
            directory_name = request.form['add_dir_name']
            if directory_name == '' or directory_name[len(directory_name) - 1] != '/' or '/' in directory_name[0:len(directory_name) - 1]:
                return redirect('/')
            user_info = retrieveUserInfo(claims)
            addDirectory(claims['email'] + user_info['current_directory'] + directory_name)
        except ValueError as exc:
            error_message = str(exc)
    return redirect('/')


'''
changeDirectoryHandler: Handles the directory change when a directory is clicked on.
                        First app route is to handled special entry "../" and the
                        second one is for any other subdirectory. Appropriate string
                        manipulation is performed and the changeCurrentDirectory()
                        is called. Returns to home page, displaying the changed
                        directory's contents.
'''
@app.route('/change_directory/', methods=['GET'], defaults={"directory_name": ""})
@app.route('/change_directory/<string:directory_name>', methods=['GET'])
def changeDirectoryHandler(directory_name):
    id_token = request.cookies.get("token")
    error_message = None
    claims = None
    times = None
    user_info = None
    current_directory = ""
    if id_token:
        try:
            claims = google.oauth2.id_token.verify_firebase_token(id_token,
            firebase_request_adapter)
            user_info = retrieveUserInfo(claims)
            current_directory = user_info['current_directory']
            if directory_name == "go_up" and current_directory != "/":
                prev_file_index =  current_directory[0:len(current_directory) - 1].rfind('/')
                prev_file_directory = current_directory[0: prev_file_index + 1]
                changeCurrentDirectory(claims['email'], prev_file_directory)
            else:
                blob_list = blobList(claims['email'] + current_directory)
                for i in blob_list:
                    if claims['email'] + current_directory + directory_name + "/" == i.name:
                        changeCurrentDirectory(claims['email'], current_directory + directory_name + "/")
                    else:
                        print("Not happening bro") #FIX
        except ValueError as exc:
            error_message = str(exc)
    return redirect('/')


'''
removeDirectoryHandler: Handles the removing of a directory when a delete button
                        associated with the directory is clicked on. Here, blobs are
                        listed inside the to be removed directory. Max results is selected
                        to be 2, because the first blob would be the directory itself. If the
                        other blob exists, removal is prevented. Depending on the existing blob,
                        file or directory, appropriate warning is displayed with flask flashes.
'''
@app.route('/remove_directory/<string:directory_name>', methods=['GET', 'POST'])
def removeDirectoryHandler(directory_name):
    id_token = request.cookies.get("token")
    error_message = None
    claims = None
    times = None
    user_info = None
    elem = None
    directory_name = directory_name + "/"
    if id_token:
        try:
            claims = google.oauth2.id_token.verify_firebase_token(id_token,
            firebase_request_adapter)
            if directory_name == '' or directory_name[len(directory_name) - 1] != '/' or '/' in directory_name[0:len(directory_name) - 1]:
                return redirect('/')
            user_info = retrieveUserInfo(claims)

            prfx = claims['email'] + user_info['current_directory']  + directory_name
            storage_client = storage.Client(project=local_constants.PROJECT_NAME)
            blobList = storage_client.list_blobs(local_constants.PROJECT_STORAGE_BUCKET,
            prefix=prfx, max_results=2)
            for i in blobList:
                if i.name != claims['email'] +  user_info['current_directory'] + directory_name:
                    if i.name[len(i.name) - 1] == '/':
                        flash("Remove the subdirectories first!")
                    else:
                        flash("Remove the files first!")
                    return redirect('/')
            removeDirectory(claims['email'] +  user_info['current_directory'] + directory_name)
        except ValueError as exc:
            error_message = str(exc)
    return redirect('/')


'''
uploadFileHandler: Handles the file upload. Attempts to upload a file to the
                   current directory. Existence of a file with the same name is
                   checked in javascript for a dynamic reaction. The script can be
                   found on index.html.
'''
@app.route('/upload_file', methods=['POST'])
def uploadFileHandler():
    id_token = request.cookies.get("token")
    error_message = None
    claims = None
    times = None
    user_info = None
    if id_token:
        try:
            claims = google.oauth2.id_token.verify_firebase_token(id_token,
            firebase_request_adapter)
            file = request.files['file_name']
            if file.filename == '':
                return redirect('/')
            user_info = retrieveUserInfo(claims)
            current_directory = user_info['current_directory']
            addFile(claims['email'] + current_directory + file.filename, file)
        except ValueError as exc:
            error_message = str(exc)
    return redirect('/')


'''
downloadFile: Handles the downloading of a file. Calls the downloadBlob() function
              and returns it with a Flask response using octet-stream mimetype.
'''
@app.route('/download_file/<string:filename>', methods=['POST'])
def downloadFile(filename):
    id_token = request.cookies.get("token")
    error_message = None
    claims = None
    times = None
    user_info = None
    if id_token:
        try:
            claims = google.oauth2.id_token.verify_firebase_token(id_token,
            firebase_request_adapter)
            user_info = retrieveUserInfo(claims)
        except ValueError as exc:
            error_message = str(exc)
    return Response(downloadBlob(claims['email'] + user_info['current_directory'] + filename), mimetype='application/octet-stream')

'''
downloadSharedFile: Handles the downloading of a shared file. Calls the downloadBlob() function
              and returns it with a Flask response using octet-stream mimetype. This was
              separated from normal file download, because the user isn't allowed direct
              access to ".sh/" directory.
'''
@app.route('/download_shared_file/<string:filename>', methods=['POST'])
def downloadSharedFile(filename):
    id_token = request.cookies.get("token")
    error_message = None
    claims = None
    times = None
    user_info = None
    file_bytes = None
    if id_token:
        try:
            claims = google.oauth2.id_token.verify_firebase_token(id_token,
            firebase_request_adapter)
            user_info = retrieveUserInfo(claims)
            sharer_email = request.form['sharer_email_hidden']
        except ValueError as exc:
            error_message = str(exc)
    return Response(downloadBlob(claims['email'] + "/.sh/" + sharer_email + "/" + filename), mimetype='application/octet-stream')

'''
removeFileHandler: Handles the removal of a file. Calls removeFile() function
                   if the user is validated.
'''
@app.route('/remove_file/<string:filename>', methods=['POST'])
def removeFileHandler(filename):
    id_token = request.cookies.get("token")
    error_message = None
    claims = None
    times = None
    user_info = None
    if id_token:
        try:
            claims = google.oauth2.id_token.verify_firebase_token(id_token,
            firebase_request_adapter)
            user_info = retrieveUserInfo(claims)
            removeFile(claims['email'] +  user_info['current_directory'] + filename)
        except ValueError as exc:
            error_message = str(exc)
    return redirect('/')


'''
root: Displays home page and all the information provided on it at any point.
      share_file and check_duplicates routes are implemented here because there
      were issues in managing the data and displaying it when they were implemented
      separately. Takes in filename variable from the URL to use it on either share_file
      or check_duplicates, depending on which button is clicked. If none provided, displays
      home page as normal.

      String manipulation to retrieve and display directories and files in the current
      directory was performed here.
      shareFile(), checkDuplicateFiles() and checkDuplicateFilesICD() functions were
      also called here, depending on the user inputs.

      Special entry for going up a directory is appended to directory_list unless it's
      the root directory.
'''
@app.route('/share_file=<string:filename>', methods=['GET','POST'])
@app.route('/check_duplicates=<string:filename>', methods=['GET','POST'])
@app.route('/', methods=['GET','POST'], defaults={'filename':''})
def root(filename):
    id_token = request.cookies.get("token")
    error_message = None
    claims = None
    times = None
    user_info = None
    file_list = []
    directory_list = []
    current_directory = "/"
    duplicate_files = []
    shared_files = []
    if id_token:
        try:
            claims = google.oauth2.id_token.verify_firebase_token(id_token,
            firebase_request_adapter)
            user_info = retrieveUserInfo(claims)
            if user_info == None:
                createUserInfo(claims)
                user_info = retrieveUserInfo(claims)
            else:
                current_directory = user_info['current_directory']

            blob_list = blobList(claims['email'] + current_directory)
            for i in blob_list: #directory list and file list
                if i.name[len(i.name) - 1] == '/':
                    i.name = i.name[len(claims['email']) + len(current_directory):]
                    if len(i.name) > 0 and i.name[0:len(i.name)-1].find('/') == -1 and i.name != ".sh/": #dont display shared folder
                        directory_list.append(i)
                else:
                    i.name = i.name[len(claims['email']) + len(current_directory):]
                    if i.name[0:len(i.name)-1].find('/') == -1:
                        file_list.append(i)

            shared_blob_list = blobList(claims['email'] + "/.sh/")
            for i in shared_blob_list:
                if i.name[len(i.name) - 1] != '/':
                    f_name_index = i.name.rfind("/")
                    email_index = i.name[0:f_name_index - 1].rfind("/")
                    f_name = i.name[f_name_index + 1:len(i.name)]
                    sharer_email = i.name[email_index + 1: f_name_index]
                    shared_files.append({"name" : f_name, "email": sharer_email})


            if current_directory != "/": #show go up a directory button
                storage_client = storage.Client(project=local_constants.PROJECT_NAME)
                bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
                blob = bucket.blob("../")
                directory_list.append(blob)

            if request.form.get("share_button"):  #share a file
                sharee_email = request.form['share_email']
                shareFile(user_info, filename, sharee_email)

            if request.form.get("check_dup_button"): #check for duplicates
                if request.form.get("boxer"):
                    duplicate_files = checkDuplicateFiles(user_info, filename)
                else:
                    duplicate_files = checkDuplicateFilesICD(user_info, filename)

        except ValueError as exc:
            error_message = str(exc)

    return render_template('index.html', user_data=claims, error_message=error_message,
    user_info=user_info, file_list=file_list, directory_list=directory_list, current_directory = current_directory, duplicate_files=duplicate_files, shared_files = shared_files)
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
