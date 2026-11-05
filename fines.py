from datetime import date

FINE_PER_DAY = 0.50

def days_late(due_date):
    return (date.today() - date.fromisoformat(due_date)).days

def fine_for(due_date):
    return max(0,days_late(due_date)) * FINE_PER_DAY

def money(amout):
    return round(float(amout),2)