'''
Handles AI-based meal recommendations.
For now, it uses basic frequency analysis of past meal choices.
'''
import database as db
from collections import Counter
import re

def get_user_meal_history(user_id: int):
    """Fetches and parses meal history for a user from spending logs."""
    history = db.get_spending_history(user_id, limit=100) # Get a decent amount of history
    meal_choices = []
    # Regex to extract meal names, assuming logs like "Meal: Item Name" or "Daily meal: Item Name"
    # or if the meal deduction was logged directly with the item name.
    # This will need to be robust based on how meal consumptions are logged.
    meal_pattern = re.compile(r"(?:Meal Suggested|Meal Consumed|Meal Purchase|Meal):\s*(.+)", re.IGNORECASE)
    
    for entry in history:
        # We are looking for deductions that correspond to meals.
        # A more robust way would be to have a specific type for meal deductions.
        if entry['amount'] < 0: # Deductions
            match = meal_pattern.search(entry['description'])
            if match:
                meal_name = match.group(1).strip()
                # Further clean up if price is in description e.g. "Rice and Stew (₱800)"
                meal_name = re.sub(r'\s*\(₱\d+(\.\d+)?\)', '', meal_name) # Corrected regex
                meal_choices.append(meal_name)
            # Fallback: if description itself is a known food item and amount matches its price (approx)
            # This is more complex and might lead to false positives.
            # For now, relying on explicit "Meal: ..." logging.
    return meal_choices

def generate_ai_recommendations(user_id: int, daily_allowance: float):
    """Generates meal recommendations based on spending history and affordability."""
    meal_history = get_user_meal_history(user_id)
    
    if not meal_history:
        return [] # No history, no specific recommendations

    meal_counts = Counter(meal_history)
    # Sort by frequency, most frequent first
    sorted_preferred_meals = [meal for meal, count in meal_counts.most_common()]

    recommendations = []
    all_food_items = db.get_all_food_items() # List of dicts with 'item_name' and 'price'
    food_item_details = {item['item_name']: item['price'] for item in all_food_items}

    for meal_name in sorted_preferred_meals:
        if meal_name in food_item_details and food_item_details[meal_name] <= daily_allowance:
            recommendations.append({"item": meal_name, "price": food_item_details[meal_name], "reason": "Based on your history"})
            if len(recommendations) >= 3: # Limit to top 3 AI recommendations
                break
    
    return recommendations

if __name__ == "__main__":
    # Test the AI recommendation logic
    db.initialize_database()
    # db.load_food_items_from_json() # Ensure food items are loaded

    # Create a dummy user and log some spending for testing
    test_user_id = 77777
    db.add_user(test_user_id)
    db.set_user_budget(test_user_id, 30000) # 1000 daily allowance
    user_data = db.get_user_data(test_user_id)
    daily_allowance_test = user_data['daily_allowance'] if user_data else 1000

    # Log some dummy meal purchases
    # db.log_spending(test_user_id, "Meal: Rice and Stew", -800)
    # db.log_spending(test_user_id, "Meal: Jollof Rice", -700)
    # db.log_spending(test_user_id, "Meal: Rice and Stew", -800)
    # db.log_spending(test_user_id, "Meal: Beans and Plantain", -600)
    # db.log_spending(test_user_id, "Meal: Rice and Stew", -850) # Price might have changed
    # db.log_spending(test_user_id, "Meal: Noodles and Egg", -500)
    # db.log_spending(test_user_id, "Meal: Jollof Rice", -700)

    print(f"Testing AI recommendations for user {test_user_id} with allowance ₱{daily_allowance_test}")
    recommendations = generate_ai_recommendations(test_user_id, daily_allowance_test)

    if recommendations:
        print("\nAI Recommended Meals:")
        for rec in recommendations:
            print(f"- {rec['item']} (₱{rec['price']}) - {rec['reason']}")
    else:
        print("\nNo specific AI recommendations could be generated based on history and budget.")

    # Test with no history (or new user)
    # new_user_id = 88888
    # db.add_user(new_user_id)
    # db.set_user_budget(new_user_id, 15000) # 500 daily
    # user_data_new = db.get_user_data(new_user_id)
    # daily_allowance_new = user_data_new['daily_allowance'] if user_data_new else 500
    # print(f"\nTesting AI recommendations for new user {new_user_id} with allowance ₱{daily_allowance_new}")
    # new_user_recs = generate_ai_recommendations(new_user_id, daily_allowance_new)
    # if not new_user_recs:
    #     print("Correctly returned no recommendations for a new user.")
    # else:
    #     print(f"Error: New user recommendations: {new_user_recs}")
pass  # Ensure the file ends with a newline character or a complete statement. Adding a pass for safety if it was empty.
