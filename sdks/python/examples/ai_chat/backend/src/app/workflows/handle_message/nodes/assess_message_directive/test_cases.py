
from app.workflows.handle_message.schemas import MessageDirective

test_cases = [
  {
    "state_input": {
      "received_message": {
        "message": "Suggest a fun date idea.",
        "chat_id": "mock_chat_id",
        "contact_id": "mock_contact_id"
      }
    },
    "state_expected": {
      "message_directive": MessageDirective.DATE_IDEA_RESEARCH
    }
  },
  {
    "state_input": {
      "received_message": {
        "message": "What do you do for work?",
        "chat_id": "mock_chat_id",
        "contact_id": "mock_contact_id"
      }
    },
    "state_expected": {
      "message_directive": MessageDirective.WORK_RELATED_RESPONSE
    }
  },
  {
    "state_input": {
      "received_message": {
        "message": "Tell me a joke.",
        "chat_id": "mock_chat_id",
        "contact_id": "mock_contact_id"
      }
    },
    "state_expected": {
      "message_directive": MessageDirective.GENERAL_RESPONSE
    }
  },
  {
    "state_input": {
      "received_message": {
        "message": "what's up?",
        "chat_id": "mock_chat_id",
        "contact_id": "mock_contact_id"
      }
    },
    "state_expected": {
      "message_directive": MessageDirective.GENERAL_RESPONSE
    }
  },
  {
    "state_input": {
      "received_message": {
        "message": "What's a good date idea we should go on?",
        "chat_id": "mock_chat_id",
        "contact_id": "mock_contact_id"
      }
    },
    "state_expected": {
      "message_directive": MessageDirective.DATE_IDEA_RESEARCH
    }
  },
  {
    "state_input": {
      "received_message": {
        "message": "Can you draw me a picture of a cat?",
        "chat_id": "mock_chat_id",
        "contact_id": "mock_contact_id"
      }
    },
    "state_expected": {
      "message_directive": MessageDirective.IMAGE_RESPONSE
    }
  },
  {
    "state_input": {
      "received_message": {
        "message": "I'd love to see something visual related to our conversation.",
        "chat_id": "mock_chat_id",
        "contact_id": "mock_contact_id"
      }
    },
    "state_expected": {
      "message_directive": MessageDirective.IMAGE_RESPONSE
    }
  }
]
