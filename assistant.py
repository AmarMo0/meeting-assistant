from dotenv import load_dotenv
from langchain.tools import tool
from langchain.agents import create_agent
from google_calendar import (
    get_calendar_service,
    create_calendar_event,
    list_calendar_events,
    delete_calendar_event
)
from datetime import datetime
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from zoneinfo import ZoneInfo


load_dotenv()

import os
calendar_id = "c15376643a3153eb1e1a45726ea8ff1cbb638b1760c290b1247a6f51ea660091@group.calendar.google.com"

def local_to_iso(value: str, timezone: str) -> str:
    local_time = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    return local_time.replace(
        tzinfo=ZoneInfo(timezone)
    ).isoformat()


def find_conflicts(start_time: str, end_time: str) -> list[dict]:
    service = get_calendar_service()

    return list_calendar_events(
        service=service,
        calendar_id=calendar_id,
        start_time=start_time,
        end_time=end_time,
    )

@tool
def book_meeting(title:str , start_time:str , end_time:str, timezone: str = "Africa/Cairo") -> dict:
    """Create a meeting in Google Calendar.

    Provide start_time and end_time as YYYY-MM-DDTHH:MM.
    Do not include seconds or UTC offsets.
    Provide timezone separately as an IANA name, such as Africa/Cairo.
    """
    start_time = local_to_iso(start_time, timezone)
    end_time = local_to_iso(end_time, timezone)

    service = get_calendar_service()
    conflicts = find_conflicts(start_time, end_time)

    if conflicts:
        return {"error": "This time overlaps an existing event."}
    
    event = create_calendar_event(
        service=service,
        calendar_id=calendar_id,
        title=title,
        start_time=start_time,
        end_time=end_time,
)

    return {
        "id": event["id"],
        "title": event["summary"],
        "start": event["start"],
        "end": event["end"],
        "link": event["htmlLink"],
}

@tool
def view_meeting(
    start_time: str,
    end_time: str,
    timezone: str = "Africa/Cairo",
) -> list[dict]:
    """Read calendar events within a period.

    Provide start_time and end_time as YYYY-MM-DDTHH:MM.
    Do not include seconds or UTC offsets.
    Provide timezone separately as an IANA name, such as Africa/Cairo.
    """

    start_time = local_to_iso(start_time, timezone)
    end_time = local_to_iso(end_time, timezone)

    service = get_calendar_service()
    events = list_calendar_events(
        service= service,
        calendar_id=calendar_id,
        start_time=start_time,
        end_time=end_time,
        
    )
    return [
        {
            "title": event.get("summary", "Untitled"),
            "start": event["start"],
            "end": event["end"],
            "id": event["id"]
        }
        for event in events
    ]
    
@tool
def delete_event(event_id: str) -> dict:
    """Delete a specific calendar event.

    Use an event ID returned by view_meeting.
    Never invent an event ID.
    """
    service = get_calendar_service()

    delete_calendar_event(
        service = service,
        calender_id = calendar_id,
        event_id = event_id
    )

    return {
    "status": "deleted",
    "event_id": event_id,
    }


agent = create_agent(
    model= 'gpt-5-nano',
    tools=[book_meeting, view_meeting, delete_event],
    checkpointer=InMemorySaver(),
    middleware=[HumanInTheLoopMiddleware(
        interrupt_on={
            "book_meeting": {
                "allowed_decisions": ["approve", "reject"]
                },
            "delete_event": {
                "allowed_decisions": ["approve", "reject"]
                },
            }  
        )   
    ],
    system_prompt=f"""
        You are a personal meeting assistant.

        The current local date and time at startup is:
        {datetime.now().astimezone().isoformat()}

        The default timezone is Africa/Cairo.
        Use Africa/Cairo when the user says "default" or omits a timezone.
        Do not infer a timezone from the computer's UTC offset.

        You have two tools:

        1. book_meeting
        - Create a meeting.
        - Establish the title, date, start time, and end time or duration.
        - Ask for missing details; do not invent them.
        - Booking approval is handled by the application.
        - If approval is rejected, say the meeting was not created.
        - Do not retry unless the user asks.
        - Confirm success only after the tool returns a successful result.
        - Include the saved title, times, and calendar link.

        2. view_meetings
        - Read events for the requested date or period.
        - For a full day, request midnight at its start through
            midnight at the start of the following day.
        - If no events are returned, say no events were found.
        - Clearly identify all-day events.

            For both tools, provide local times as YYYY-MM-DDTHH:MM.
            Do not include seconds or UTC offsets.
            Pass the IANA timezone separately using the timezone argument.
            Python calculates the UTC offsets.

            Use tools for calendar information; do not invent events.
            Reading events does not require approval.
            Do not create a meeting when the user only asks to view their schedule.

            You can delete meetings using delete_event.
            First use view_meeting to find the intended event and its ID.
            If multiple events match, ask the user which one they mean.
            Never invent event IDs.
            Deletion approval is handled by the application.
            Confirm deletion only after the tool reports success.
            You cannot edit meetings, add attendees, or set reminders.
            """
 
)

def review_action(action: dict) -> dict:
    args = action["args"]
    tool_name = action["name"]

    if tool_name == "book_meeting":
        timezone = args.get("timezone", "Africa/Cairo")
        start = local_to_iso(args["start_time"], timezone)
        end = local_to_iso(args["end_time"], timezone)

        if find_conflicts(start, end):
            print("\nBooking blocked: this time is occupied.")

            return {
                "type": "reject",
                "message": (
                    "Overlapping events were found. "
                    "No meeting was created. Ask for another time."
                ),
            }

        print("\nProposed booking")
        print("Title:", args["title"])
        print("Start:", start)
        print("End:", end)
        print("Timezone:", timezone)

    elif tool_name == "delete_event":
        service = get_calendar_service()

        event = service.events().get(
            calendarId=calendar_id,
            eventId=args["event_id"],
        ).execute()

        print("\nProposed deletion")
        print("Title:", event.get("summary", "Untitled"))
        print("Start:", event["start"])
        print("End:", event["end"])
        print("Event ID:", event["id"])

    else:
        return {
            "type": "reject",
            "message": "This action has no configured approval handler.",
        }

    answer = input("Approve this action? (yes/no): ").strip().lower()

    if answer == "yes":
        return {"type": "approve"}

    return {
        "type": "reject",
        "message": "The user rejected this action. Do not retry unless asked.",
    }


def main():
    config = {"configurable": {"thread_id": "meeting-assistant"}}

    print("Meeting assistant. Type 'exit' to stop.")

    while True:
        user_message = input("\nYou: ").strip()

        if user_message.lower() == "exit":
            break

        if not user_message:
            continue

        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_message}]},
            config=config,
        )

        while result.get("__interrupt__"):
            decisions = []

            for interrupt in result["__interrupt__"]:
                for action in interrupt.value["action_requests"]:
                    decision = review_action(action)
                    decisions.append(decision)

            result = agent.invoke(
                Command(resume={"decisions": decisions}),
                config=config,
            )

        print("\nAssistant:", result["messages"][-1].content)


if __name__ == "__main__":
    main()