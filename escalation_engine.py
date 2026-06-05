# Escalation Engine for AgentOptima

class EscalationDetector:
    def __init__(self):
        self.threshold = 0.75  # Confidence threshold for escalation
        self.escalation_count = 0
        self.max_escalations = 3  # Limit escalations to prevent cycles

    def evaluate_response(self, response):
        # Logic to evaluate if a response needs escalation
        if response['confidence'] < self.threshold:
            self.escalation_count += 1
            return self.escalation_count <= self.max_escalations  # Allow escalation up to limit
        self.escalation_count = 0
        return False
    def __init__(self):
        self.threshold = 0.75  # Confidence threshold for escalation

    def evaluate_response(self, response):
        # Logic to evaluate if a response needs escalation
        if response['confidence'] < self.threshold:
            return True  # Needs escalation
        return False  

class EscalationLadder:
    def __init__(self):
        self.models = [
            'openrouter/anthropic/claude-sonnet-4-6',  # Highest tier
            'openrouter/anthropic/claude-haiku-4-5'
        ]

    def get_next_model(self, current_model):
        current_index = self.models.index(current_model)
        if current_index + 1 < len(self.models):
            return self.models[current_index + 1]  # Escalate to next model
        return current_model  # Already at highest tier

class ContextHandoff:
    @staticmethod
    def transfer_context(old_context, new_context):
        # Logic to maintain context when escalating
        return new_context.update(old_context)
