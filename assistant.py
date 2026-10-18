from dotenv import load_dotenv
from langchain.tools import tool
from langchain.agents import create_agent
from google_calendar import (
    get_calendar_service,
    create_calendar_event,
    list_calendar_events,
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
    conflict = list_calendar_events(
        service= service,
        calendar_id=calendar_id,
        start_time=start_time,
        end_time=end_time,
    )
    if conflict:
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
        }
        for event in events
    ]
    

agent = create_agent(
    model= 'gpt-5-nano',
    tools=[book_meeting, view_meeting],
    checkpointer=InMemorySaver(),
    middleware=[HumanInTheLoopMiddleware(
        interrupt_on={
                "book_meeting": {
                    "allowed_decisions": ["approve", "reject"]
                }
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

            You cannot edit or delete meetings, add attendees, or set reminders.
            Do not offer these actions.
            Keep replies concise.
            """
 
)

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
                    print("\nProposed action:", action["name"])

                    for name, value in action["args"].items():
                        print(f"  {name}: {value}")

                    answer = input("Approve this booking? (yes/no): ")
                    approved = answer.strip().lower() == "yes"

                    decisions.append(
                        {"type": "approve"}
                        if approved
                        else {
                            "type": "reject",
                            "message": "The user rejected this booking.",
                        }
                    )

            result = agent.invoke(
                Command(resume={"decisions": decisions}),
                config=config,
            )

        print("\nAssistant:", result["messages"][-1].content)


if __name__ == "__main__":
    main()