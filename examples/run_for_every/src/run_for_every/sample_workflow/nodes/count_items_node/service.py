# Example service function
async def count_items(items: list[str]) -> int:
    print("Running count_items...")

    count = len(items)
    return count
