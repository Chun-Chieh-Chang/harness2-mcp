"""Tiny calculator library."""

def add(a, b):
    return a + b

def mul(a, b):
    return a * b

def avg(nums):
    if not nums:
        raise ValueError("avg() of empty sequence")
    return sum(nums) / len(nums)

def discount(price, pct):
    """Return price reduced by pct percent."""
    return price * (1 - pct / 100)

def compound(principal, rate, years):
    """Return compound interest: principal*(1+rate)**years."""
    return principal * (1 + rate) ** years
