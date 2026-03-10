import os
import gspread 
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials
import json



class GoogleDriveServiceDict:
    def __init__(self, credentials_dict):
        self._SCOPES=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        self.cred_dict = credentials_dict
        

    def build_drive(self):
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.cred_dict, self._SCOPES)
        service = build('drive', 'v3', credentials=creds)

        return service
        
    def build_sheet(self):       
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.cred_dict, self._SCOPES)
        service = gspread.authorize(creds) 

        return service



class GoogleDriveService:
    def __init__(self, cred_path):
        self._SCOPES=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        self.cred_path = cred_path
        

    def build_drive(self):
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.cred_path, self._SCOPES)
        service = build('drive', 'v3', credentials=creds)

        return service
        
    def build_sheet(self):

        b = BytesIO()
        b.write(json.dumps(d).encode())
        json.load(b)
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.cred_path, self._SCOPES)
        service = gspread.authorize(creds) 

        return service
