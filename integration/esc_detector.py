class EscalationDetector:
    def __init__(self, max_escalations=3):
        self.max_escalations = max_escalations
        self.escalation_count = 0
        self.last_model = None

    def should_escalate(self, current_model, confidence):
        if self.escalation_count >= self.max_escalations:
            return False
        if confidence < 0.70:  # Threshold can be adjusted
            self.escalation_count += 1
            self.last_model = current_model
            return True
        return False

    def reset(self):
        self.escalation_count = 0
        self.last_model = None

# Usage:
# esc_detector = EscalationDetector()
# if esc_detector.should_escalate(current_model, confidence):
#     # logic for escalation