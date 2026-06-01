"""
requestState Module — S2C ka "Dimaag"

Yeh woh encoded string hai jo server ka current kaam ka status save karta hai.
Jaise form bhar ke submit kiya, page refresh ho gaya, lekin draft save tha —
dobara bheja aur kaam continue!

requestState = encoded JSON jisme hota hai:
  - original_request: jo user ne manga tha
  - progress: kitna kaam ho gaya
  - pending_question: kya poochna hai
  - round_count: kitni baar elicitation ho chuka
"""
import json
import base64
import hmac
import hashlib
from django.conf import settings
from django.core.signing import Signer, BadSignature

class RequestStateEncoder:
    """
    Server ka kaam ka state encode karta hai.
    JWT jaisa — but simpler. Django Signer use karta hai.
    """

    @staticmethod
    def encode(state_dict: dict) -> str:
        """
        State dict ko signed string mein convert karo.
        Tamper-proof hai — agar client change kare toh detect ho jayega.
        """
        signer = Signer(key=settings.REQUEST_STATE_SECRET, salt='s2c-request-state')
        json_str = json.dumps(state_dict, sort_keys=True)
        signed = signer.sign(json_str)
        # Base64 encode for safe transport
        return base64.urlsafe_b64encode(signed.encode()).decode().rstrip('=')

    @staticmethod
    def decode(encoded_state: str) -> dict:
        """
        Signed string ko wapas state dict mein convert karo.
        Agar tampered hai toh BadSignature raise hoga.
        """
        signer = Signer(key=settings.REQUEST_STATE_SECRET, salt='s2c-request-state')
        # Add padding back if needed
        padding = 4 - len(encoded_state) % 4
        if padding != 4:
            encoded_state += '=' * padding
        signed = base64.urlsafe_b64decode(encoded_state.encode()).decode()
        json_str = signer.unsign(signed)
        return json.loads(json_str)


class ElicitationResponse:
    """
    Special Response jisme server client se poochta hai.

    Format:
    {
        "status": "ELICITATION_REQUIRED",
        "question": "Kya 3 files delete karun?",
        "requestState": "eyJzdGF0ZSI6ICJkZWxldGluZyJ9...",
        "options": ["yes", "no"],  # optional
        "hint": "User ko dikhane ke liye message"
    }
    """

    @staticmethod
    def build(question: str, request_state_dict: dict, options=None, hint=None):
        encoded_state = RequestStateEncoder.encode(request_state_dict)
        response = {
            "status": "ELICITATION_REQUIRED",
            "question": question,
            "requestState": encoded_state,
        }
        if options:
            response["options"] = options
        if hint:
            response["hint"] = hint
        return response


class ElicitationRequest:
    """
    Client ka retry request jisme answer + requestState hota hai.

    Format:
    {
        "action": "delete_files",
        "files": ["a.txt", "b.txt", "c.txt"],
        "answer": "yes",  # <-- User ka jawab
        "requestState": "eyJzdGF0ZSI6ICJkZWxldGluZyJ9..."  # <-- Server ka state
    }
    """

    @staticmethod
    def parse(data: dict) -> tuple:
        """
        Returns: (original_action, answer, decoded_state_dict)
        Raises: ValueError agar requestState invalid hai
        """
        encoded_state = data.get('requestState')
        if not encoded_state:
            raise ValueError("requestState missing. Pehli request hai ya retry?")

        state = RequestStateEncoder.decode(encoded_state)
        answer = data.get('answer')
        if answer is None:
            raise ValueError("answer missing. User ne kya bola?")

        original_action = state.get('original_action')
        return original_action, answer, state
