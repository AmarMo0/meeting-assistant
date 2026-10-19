import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

def create_calendar_event(service, calendar_id, title, start_time, end_time):
    event = {
        "summary": title,
        "start": {
            "dateTime": start_time,
        },
        "end": {
            "dateTime": end_time,
        },
    }

    created_event = service.events().insert(
        calendarId=calendar_id,
        body=event,
    ).execute()

    return created_event

def get_calendar_service():
    """Authorize access and return a Google Calendar API client."""
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json", SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

def delete_calendar_event(service, calender_id, event_id):
    service.events().delete(
    calendarId=calender_id,
    eventId=event_id,
    ).execute()



def list_calendar_events(service, calendar_id, start_time, end_time):
    result = service.events().list(
        calendarId=calendar_id,
        timeMin=start_time,
        timeMax=end_time,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return result.get("items", [])
