"""
S2C (Server-to-Client) Elicitation Views

Flow:
1. Client sends request → Server processes
2. Server needs input → Returns Special Response (question + requestState)
3. Client asks user, gets answer
4. Client retries SAME request + answer + requestState
5. Any server picks it up, decodes requestState, continues work
6. Final response → Kaam complete!

Rules followed:
- In-Flight Rule: Server sirf tab poochta hai jab ALREADY request process kar raha ho
- Special Response Rule: Response mein "question" + "requestState" hota hai
- Stateless: Koi session nahi, koi open connection nahi
"""
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.conf import settings
from .models import FileRecord, ElicitationLog
from .auth import APIKeyAuthentication
from .request_state import RequestStateEncoder, ElicitationResponse, ElicitationRequest

# ==========================
# DEMO 1: File Deletion with Elicitation
# ==========================

@api_view(['POST'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def delete_files(request):
    """
    POST /api/files/delete/

    S2C Elicitation Demo:
    - Pehli request: {"files": ["a.txt", "b.txt", "c.txt"]}
      → Server: "Kya delete karun?" (Special Response with requestState)

    - Retry request: {"files": [...], "answer": "yes", "requestState": "..."}
      → Server decodes state, deletes files, returns success

    Koi bhi server instance retry handle kar sakti hai!
    """
    data = request.data
    files = data.get('files', [])
    answer = data.get('answer')
    request_state = data.get('requestState')

    if not files:
        return Response({"error": "files list chahiye"}, status=400)

    # --- CASE 1: Retry with answer + requestState ---
    if request_state and answer is not None:
        try:
            original_action, user_answer, state = ElicitationRequest.parse(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        # Validate: yeh wahi action hai jo shuru kiya tha?
        if original_action != 'delete_files':
            return Response({"error": "Action mismatch. Tampering?"}, status=400)

        # Check round count
        round_count = state.get('round_count', 0)
        if round_count >= settings.MAX_ELICITATION_ROUNDS:
            return Response({"error": "Max elicitation rounds reached."}, status=400)

        # Process based on answer
        if user_answer.lower() in ['yes', 'y', 'haan', 'true']:
            file_names = state.get('files', [])
            deleted = []
            not_found = []

            for fname in file_names:
                try:
                    f = FileRecord.objects.get(name=fname, is_deleted=False)
                    f.is_deleted = True
                    f.save()
                    deleted.append(fname)
                except FileRecord.DoesNotExist:
                    not_found.append(fname)

            # Log the elicitation
            ElicitationLog.objects.create(
                action='delete_files',
                question=state.get('question', ''),
                answer=user_answer,
                request_state=request_state,
                round_number=round_count + 1
            )

            return Response({
                "status": "SUCCESS",
                "message": "Files deleted! Kaam complete!",
                "action": "delete_files",
                "deleted": deleted,
                "not_found": not_found,
                "server_note": "Koi bhi server ne handle kiya — requestState mein sab tha!",
                "elicitation_rounds": round_count + 1
            })
        else:
            return Response({
                "status": "CANCELLED",
                "message": "User ne mana kar diya. Kuch delete nahi hua.",
                "action": "delete_files"
            })

    # --- CASE 2: First request — needs elicitation ---
    # Check if files exist
    existing_files = []
    for fname in files:
        if FileRecord.objects.filter(name=fname, is_deleted=False).exists():
            existing_files.append(fname)

    if not existing_files:
        return Response({
            "status": "NOT_FOUND",
            "message": "Koi file hi nahi mili. Elicitation ki zaroorat nahi."
        })

    # Build requestState: server ka current kaam ka status
    state_dict = {
        "original_action": "delete_files",
        "files": existing_files,
        "question": f"Kya {len(existing_files)} files delete karun?",
        "round_count": 0,
        "timestamp": str(__import__('datetime').datetime.now()),
        "server_instance": "any"  # Koi bhi server!
    }

    # Return Special Response (Elicitation Required)
    return Response(
        ElicitationResponse.build(
            question=f"Kya {len(existing_files)} files delete karun? ({', '.join(existing_files)})",
            request_state_dict=state_dict,
            options=["yes", "no"],
            hint="Ye files permanently delete ho jayengi."
        ),
        status=202  # Accepted but needs input
    )


# ==========================
# DEMO 2: Generic S2C Action with Multiple Elicitations
# ==========================

@api_view(['POST'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def process_with_elicitation(request):
    """
    POST /api/process/

    Generic S2C handler jo multiple elicitation rounds support karta hai.
    Example: "Konsa folder?" → "Konsa format?" → "Confirm?" → Done
    """
    data = request.data
    action = data.get('action', 'unknown')
    answer = data.get('answer')
    request_state = data.get('requestState')

    # --- Retry with state ---
    if request_state:
        try:
            _, user_answer, state = ElicitationRequest.parse(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        round_count = state.get('round_count', 0) + 1
        collected = state.get('collected_answers', {})
        collected[f"round_{round_count}"] = user_answer

        # Check if we need MORE elicitation
        pending_questions = state.get('pending_questions', [])

        if round_count < len(pending_questions):
            # Still need more answers
            next_question = pending_questions[round_count]
            new_state = {
                "original_action": action,
                "collected_answers": collected,
                "pending_questions": pending_questions,
                "round_count": round_count,
                "total_rounds": len(pending_questions)
            }
            return Response(
                ElicitationResponse.build(
                    question=next_question,
                    request_state_dict=new_state,
                    hint=f"Round {round_count + 1} of {len(pending_questions)}"
                ),
                status=202
            )
        else:
            # All questions answered — process!
            return Response({
                "status": "SUCCESS",
                "message": "Sara input mil gaya! Processing complete.",
                "collected_answers": collected,
                "total_rounds": round_count,
                "server_note": "Multi-round elicitation complete!"
            })

    # --- First request — define questions ---
    # Example: File export workflow
    if action == 'export_files':
        questions = [
            "Konsa format chahiye? (csv/json/xml)",
            "Kya header row include karni hai? (yes/no)",
            "Confirm: Export karun? (yes/no)"
        ]
        state_dict = {
            "original_action": action,
            "pending_questions": questions,
            "collected_answers": {},
            "round_count": 0,
            "total_rounds": len(questions)
        }
        return Response(
            ElicitationResponse.build(
                question=questions[0],
                request_state_dict=state_dict,
                options=["csv", "json", "xml"],
                hint="Step 1 of 3"
            ),
            status=202
        )

    return Response({"error": f"Unknown action: {action}"}, status=400)


# ==========================
# DEMO 3: Auto Rickshaw Example (from the image!)
# ==========================

@api_view(['POST'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def book_ride(request):
    """
    POST /api/ride/book/

    Real-life example: Auto mein baitho, driver poochta hai:
    "Kaunse gate pe jaana hai?" (mid-trip question)

    S2C mein: Server ride process kar raha hai, beech mein poochta hai.
    """
    data = request.data
    destination = data.get('destination')
    answer = data.get('answer')
    request_state = data.get('requestState')

    if request_state:
        try:
            _, user_answer, state = ElicitationRequest.parse(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        # Continue ride with gate info
        return Response({
            "status": "RIDE_CONFIRMED",
            "message": f"Ride confirmed! {state['destination']} ke {user_answer} gate pe drop kar dunga.",
            "driver_says": "Connaught Place chalao — kaunse gate pe?",
            "user_answered": user_answer,
            "fare_estimate": state.get('fare_estimate'),
            "server_note": "requestState mein ride details the, koi bhi server continue kar sakta tha!"
        })

    if not destination:
        return Response({"error": "destination chahiye"}, status=400)

    # Mid-trip elicitation: kaunse gate?
    state_dict = {
        "original_action": "book_ride",
        "destination": destination,
        "fare_estimate": 120,
        "round_count": 0
    }

    return Response(
        ElicitationResponse.build(
            question=f"{destination} ke kaunse gate pe jaana hai?",
            request_state_dict=state_dict,
            options=["Gate 1", "Gate 2", "Gate 3", "Main Gate"],
            hint="Driver ne beech mein poocha — S2C elicitation!"
        ),
        status=202
    )


# ==========================
# Utility Endpoints
# ==========================

@api_view(['GET'])
def health_check(request):
    """GET /api/health/ — Stateless + S2C mode check"""
    return Response({
        "status": "healthy",
        "mode": "S2C_Elicitation",
        "session": "nahi_hai",
        "connection": "nahi_hai",
        "requestState": "encoded_state_carries_all_context",
        "message": "Server-to-Client baat bina connection ke!"
    })

@api_view(['GET'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def list_files(request):
    """GET /api/files/ — List all files (demo data)"""
    files = FileRecord.objects.filter(is_deleted=False).values('id', 'name', 'size_kb')
    return Response({
        "status": "ok",
        "count": len(files),
        "data": list(files)
    })

@api_view(['POST'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def create_file(request):
    """POST /api/files/create/ — Create demo file"""
    data = request.data
    name = data.get('name')
    size = data.get('size_kb', 100)
    if not name:
        return Response({"error": "name chahiye"}, status=400)
    f = FileRecord.objects.create(name=name, size_kb=size)
    return Response({
        "status": "created",
        "file": {"id": f.id, "name": f.name, "size_kb": f.size_kb}
    }, status=201)

@api_view(['GET'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def elicitation_logs(request):
    """GET /api/logs/ — See all elicitation rounds"""
    logs = ElicitationLog.objects.all().order_by('-created_at').values(
        'action', 'question', 'answer', 'round_number', 'created_at'
    )
    return Response({
        "status": "ok",
        "count": len(logs),
        "data": list(logs)
    })
