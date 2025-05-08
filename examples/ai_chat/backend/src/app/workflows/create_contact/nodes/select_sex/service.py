import random

from app.db.models.contact.schemas import Sex


def select_sex() -> Sex:
    """
    Returns a random Sex:
      - 0.015% chance of OTHER
      - remaining 99.985% split equally between MALE and FEMALE
    """
    other_prob = 0.00015
    half_prob = (1.0 - other_prob) / 2.0

    r = random.random()
    if r < other_prob:
        return Sex.OTHER
    elif r < other_prob + half_prob:
        return Sex.MALE
    else:
        return Sex.FEMALE
