"""
Meal Planning and Recommendation Service
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, date, timedelta
from dataclasses import dataclass, asdict
import asyncio
from enum import Enum
from .base_service import BaseService

logger = logging.getLogger(__name__)

class MealType(Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"

class DietaryPreference(Enum):
    NONE = "none"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    GLUTEN_FREE = "gluten_free"
    KETO = "keto"
    PALEO = "paleo"

@dataclass
class MealItem:
    """Individual meal item"""
    name: str
    meal_type: MealType
    estimated_cost: float
    calories: Optional[int] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    dietary_tags: List[str] = None
    
    def __post_init__(self):
        if self.dietary_tags is None:
            self.dietary_tags = []

@dataclass
class MealPlan:
    """Daily meal plan"""
    user_id: int
    plan_date: date
    breakfast: Optional[MealItem] = None
    lunch: Optional[MealItem] = None
    dinner: Optional[MealItem] = None
    snacks: List[MealItem] = None
    total_cost: float = 0.0
    total_calories: int = 0
    created_at: datetime = None
    
    def __post_init__(self):
        if self.snacks is None:
            self.snacks = []
        if self.created_at is None:
            self.created_at = datetime.now()
        
        # Calculate totals
        self._calculate_totals()
    
    def _calculate_totals(self):
        """Calculate total cost and calories"""
        meals = [self.breakfast, self.lunch, self.dinner] + self.snacks
        meals = [meal for meal in meals if meal is not None]
        
        self.total_cost = sum(meal.estimated_cost for meal in meals)
        self.total_calories = sum(meal.calories or 0 for meal in meals)

@dataclass
class UserDietaryProfile:
    """User's dietary preferences and restrictions"""
    user_id: int
    dietary_preference: DietaryPreference = DietaryPreference.NONE
    allergies: List[str] = None
    dislikes: List[str] = None
    daily_calorie_goal: Optional[int] = None
    daily_budget: Optional[float] = None
    preferred_cuisines: List[str] = None
    
    def __post_init__(self):
        if self.allergies is None:
            self.allergies = []
        if self.dislikes is None:
            self.dislikes = []
        if self.preferred_cuisines is None:
            self.preferred_cuisines = []

class MealService(BaseService):
    """Meal planning and recommendation service"""
    
    def __init__(self):
        super().__init__("meal_service")
        self.meal_database = {}  # Will be loaded from food_data.json
        self.ai_recommender = None
    
    async def initialize(self) -> bool:
        """Initialize the meal service"""
        try:
            self.db = self.get_dependency("database_service")
            if not self.db:
                logger.error("Database service not available")
                return False
            
            # Load meal database
            await self._load_meal_database()
            
            # Create meal-related tables
            await self._create_meal_tables()
            
            # Initialize AI recommender if available
            await self._initialize_ai_recommender()
            
            logger.info("Meal service initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize meal service: {e}")
            return False
    
    async def _load_meal_database(self):
        """Load meal database from food_data.json"""
        try:
            import json
            import os
            
            food_data_path = os.path.join(os.path.dirname(__file__), '..', 'food_data.json')
            
            if os.path.exists(food_data_path):
                with open(food_data_path, 'r') as f:
                    food_data = json.load(f)
                
                # Convert to MealItem objects
                for category, items in food_data.items():
                    if isinstance(items, dict):
                        for item_name, item_data in items.items():
                            if isinstance(item_data, dict):
                                meal_item = MealItem(
                                    name=item_name,
                                    meal_type=MealType.LUNCH,  # Default, can be customized
                                    estimated_cost=item_data.get('price', 0.0),
                                    calories=item_data.get('calories'),
                                    dietary_tags=item_data.get('tags', [])
                                )
                                
                                # Store in database
                                if category not in self.meal_database:
                                    self.meal_database[category] = []
                                self.meal_database[category].append(meal_item)
                
                logger.info(f"Loaded {sum(len(items) for items in self.meal_database.values())} meal items")
            else:
                logger.warning("food_data.json not found, using default meal database")
                await self._create_default_meals()
                
        except Exception as e:
            logger.error(f"Error loading meal database: {e}")
            await self._create_default_meals()
    
    async def _create_default_meals(self):
        """Create default meal items if food_data.json is not available"""
        default_meals = {
            "breakfast": [
                MealItem("Oatmeal with fruits", MealType.BREAKFAST, 5.0, 350, dietary_tags=["healthy", "vegetarian"]),
                MealItem("Scrambled eggs with toast", MealType.BREAKFAST, 7.0, 400),
                MealItem("Pancakes", MealType.BREAKFAST, 8.0, 450),
            ],
            "lunch": [
                MealItem("Grilled chicken salad", MealType.LUNCH, 12.0, 450, dietary_tags=["healthy", "protein"]),
                MealItem("Vegetable stir-fry", MealType.LUNCH, 10.0, 350, dietary_tags=["vegetarian", "healthy"]),
                MealItem("Beef sandwich", MealType.LUNCH, 15.0, 550),
            ],
            "dinner": [
                MealItem("Grilled salmon with vegetables", MealType.DINNER, 20.0, 500, dietary_tags=["healthy", "protein"]),
                MealItem("Pasta with marinara sauce", MealType.DINNER, 12.0, 600, dietary_tags=["vegetarian"]),
                MealItem("Chicken curry with rice", MealType.DINNER, 18.0, 650),
            ]
        }
        
        self.meal_database = default_meals
    
    async def _create_meal_tables(self):
        """Create meal-related database tables"""
        meal_plans_sql = """
        CREATE TABLE IF NOT EXISTS meal_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan_date DATE,
            breakfast_data TEXT,
            lunch_data TEXT,
            dinner_data TEXT,
            snacks_data TEXT,
            total_cost DECIMAL(10,2),
            total_calories INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            UNIQUE(user_id, plan_date)
        );
        """
        
        dietary_profiles_sql = """
        CREATE TABLE IF NOT EXISTS dietary_profiles (
            user_id INTEGER PRIMARY KEY,
            dietary_preference VARCHAR(20) DEFAULT 'none',
            allergies TEXT,
            dislikes TEXT,
            daily_calorie_goal INTEGER,
            daily_budget DECIMAL(10,2),
            preferred_cuisines TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        );
        """
        
        meal_history_sql = """
        CREATE TABLE IF NOT EXISTS meal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            meal_name VARCHAR(200),
            meal_type VARCHAR(20),
            cost DECIMAL(10,2),
            calories INTEGER,
            consumed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        );
        """
        
        await self.db.execute_query(meal_plans_sql)
        await self.db.execute_query(dietary_profiles_sql)
        await self.db.execute_query(meal_history_sql)
    
    async def _initialize_ai_recommender(self):
        """Initialize AI recommendation system"""
        try:
            # Import and initialize AI recommender
            import ai_recommendation
            self.ai_recommender = ai_recommendation
            logger.info("AI recommender initialized")
        except Exception as e:
            logger.warning(f"AI recommender not available: {e}")
    
    async def create_meal_plan(self, user_id: int, plan_date: date, 
                             budget_limit: Optional[float] = None) -> Optional[MealPlan]:
        """Create a meal plan for a user for a specific date"""
        try:
            # Get user's dietary profile
            profile = await self.get_dietary_profile(user_id)
            
            # Get budget constraint
            if budget_limit is None and profile and profile.daily_budget:
                budget_limit = profile.daily_budget
            elif budget_limit is None:
                # Get from budget service
                budget_service = self.get_dependency("budget_service")
                if budget_service:
                    budget_info = await budget_service.get_budget_info(user_id)
                    if budget_info:
                        # Assume daily budget is monthly budget / 30
                        budget_limit = float(budget_info.current_budget) / 30
            
            # Generate meal recommendations
            breakfast = await self._recommend_meal(MealType.BREAKFAST, profile, budget_limit)
            lunch = await self._recommend_meal(MealType.LUNCH, profile, budget_limit)
            dinner = await self._recommend_meal(MealType.DINNER, profile, budget_limit)
            
            # Create meal plan
            meal_plan = MealPlan(
                user_id=user_id,
                plan_date=plan_date,
                breakfast=breakfast,
                lunch=lunch,
                dinner=dinner
            )
            
            # Save to database
            await self._save_meal_plan(meal_plan)
            
            return meal_plan
            
        except Exception as e:
            logger.error(f"Error creating meal plan for user {user_id}: {e}")
            return None
    
    async def _recommend_meal(self, meal_type: MealType, profile: Optional[UserDietaryProfile], 
                            budget_limit: Optional[float]) -> Optional[MealItem]:
        """Recommend a meal based on preferences and constraints"""
        try:
            # Get available meals for this type
            available_meals = []
            
            # Check each category in meal database
            for category, meals in self.meal_database.items():
                for meal in meals:
                    # Check if meal type matches or is flexible
                    if meal.meal_type == meal_type or meal_type == MealType.LUNCH:
                        # Check dietary restrictions
                        if profile and not self._matches_dietary_profile(meal, profile):
                            continue
                        
                        # Check budget constraint
                        if budget_limit and meal.estimated_cost > budget_limit * 0.4:  # Max 40% of daily budget per meal
                            continue
                        
                        available_meals.append(meal)
            
            if not available_meals:
                return None
            
            # Use AI recommender if available
            if self.ai_recommender and profile:
                try:
                    # Get AI recommendation
                    recommended_meal = await self._get_ai_recommendation(
                        available_meals, meal_type, profile
                    )
                    if recommended_meal:
                        return recommended_meal
                except Exception as e:
                    logger.warning(f"AI recommendation failed: {e}")
            
            # Fallback to simple selection
            # Prefer healthier options
            healthy_meals = [m for m in available_meals if "healthy" in m.dietary_tags]
            if healthy_meals:
                return min(healthy_meals, key=lambda x: x.estimated_cost)
            
            return min(available_meals, key=lambda x: x.estimated_cost)
            
        except Exception as e:
            logger.error(f"Error recommending meal: {e}")
            return None
    
    async def _get_ai_recommendation(self, available_meals: List[MealItem], 
                                   meal_type: MealType, profile: UserDietaryProfile) -> Optional[MealItem]:
        """Get AI-based meal recommendation"""
        try:
            # Prepare meal data for AI
            meal_data = []
            for meal in available_meals:
                meal_data.append({
                    "name": meal.name,
                    "type": meal.meal_type.value,
                    "cost": meal.estimated_cost,
                    "calories": meal.calories,
                    "tags": meal.dietary_tags
                })
            
            # Prepare user profile
            user_profile = {
                "dietary_preference": profile.dietary_preference.value,
                "allergies": profile.allergies,
                "dislikes": profile.dislikes,
                "preferred_cuisines": profile.preferred_cuisines
            }
            
            # Get AI recommendation
            recommendation = await asyncio.get_event_loop().run_in_executor(
                None, 
                self.ai_recommender.get_meal_recommendation,
                meal_data, 
                user_profile
            )
            
            if recommendation:
                # Find the recommended meal
                for meal in available_meals:
                    if meal.name == recommendation.get("name"):
                        return meal
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting AI recommendation: {e}")
            return None
    
    def _matches_dietary_profile(self, meal: MealItem, profile: UserDietaryProfile) -> bool:
        """Check if meal matches user's dietary profile"""
        # Check dietary preference
        if profile.dietary_preference == DietaryPreference.VEGETARIAN:
            if "vegetarian" not in meal.dietary_tags and "vegan" not in meal.dietary_tags:
                return False
        elif profile.dietary_preference == DietaryPreference.VEGAN:
            if "vegan" not in meal.dietary_tags:
                return False
        elif profile.dietary_preference == DietaryPreference.GLUTEN_FREE:
            if "gluten_free" not in meal.dietary_tags:
                return False
        
        # Check allergies
        if profile.allergies:
            for allergy in profile.allergies:
                if allergy.lower() in meal.name.lower():
                    return False
        
        # Check dislikes
        if profile.dislikes:
            for dislike in profile.dislikes:
                if dislike.lower() in meal.name.lower():
                    return False
        
        return True
    
    async def _save_meal_plan(self, meal_plan: MealPlan) -> bool:
        """Save meal plan to database"""
        try:
            import json
            
            # Convert meals to JSON
            breakfast_data = json.dumps(asdict(meal_plan.breakfast)) if meal_plan.breakfast else None
            lunch_data = json.dumps(asdict(meal_plan.lunch)) if meal_plan.lunch else None
            dinner_data = json.dumps(asdict(meal_plan.dinner)) if meal_plan.dinner else None
            snacks_data = json.dumps([asdict(snack) for snack in meal_plan.snacks]) if meal_plan.snacks else None
            
            query = """
            INSERT OR REPLACE INTO meal_plans 
            (user_id, plan_date, breakfast_data, lunch_data, dinner_data, snacks_data, total_cost, total_calories, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            return await self.db.execute_query(
                query,
                (
                    meal_plan.user_id,
                    meal_plan.plan_date.isoformat(),
                    breakfast_data,
                    lunch_data,
                    dinner_data,
                    snacks_data,
                    meal_plan.total_cost,
                    meal_plan.total_calories,
                    meal_plan.created_at.isoformat()
                )
            )
            
        except Exception as e:
            logger.error(f"Error saving meal plan: {e}")
            return False
    
    async def get_meal_plan(self, user_id: int, plan_date: date) -> Optional[MealPlan]:
        """Get meal plan for a specific date"""
        try:
            query = """
            SELECT * FROM meal_plans 
            WHERE user_id = ? AND plan_date = ?
            """
            
            result = await self.db.fetch_one(query, (user_id, plan_date.isoformat()))
            if not result:
                return None
            
            import json
            
            # Parse meal data
            breakfast = None
            lunch = None
            dinner = None
            snacks = []
            
            if result['breakfast_data']:
                breakfast_dict = json.loads(result['breakfast_data'])
                breakfast = MealItem(**breakfast_dict)
            
            if result['lunch_data']:
                lunch_dict = json.loads(result['lunch_data'])
                lunch = MealItem(**lunch_dict)
            
            if result['dinner_data']:
                dinner_dict = json.loads(result['dinner_data'])
                dinner = MealItem(**dinner_dict)
            
            if result['snacks_data']:
                snacks_list = json.loads(result['snacks_data'])
                snacks = [MealItem(**snack) for snack in snacks_list]
            
            return MealPlan(
                user_id=user_id,
                plan_date=plan_date,
                breakfast=breakfast,
                lunch=lunch,
                dinner=dinner,
                snacks=snacks,
                total_cost=result['total_cost'],
                total_calories=result['total_calories'],
                created_at=datetime.fromisoformat(result['created_at'])
            )
            
        except Exception as e:
            logger.error(f"Error getting meal plan: {e}")
            return None
    
    async def get_dietary_profile(self, user_id: int) -> Optional[UserDietaryProfile]:
        """Get user's dietary profile"""
        try:
            query = """
            SELECT * FROM dietary_profiles WHERE user_id = ?
            """
            
            result = await self.db.fetch_one(query, (user_id,))
            if not result:
                return None
            
            import json
            
            allergies = json.loads(result['allergies']) if result['allergies'] else []
            dislikes = json.loads(result['dislikes']) if result['dislikes'] else []
            preferred_cuisines = json.loads(result['preferred_cuisines']) if result['preferred_cuisines'] else []
            
            return UserDietaryProfile(
                user_id=user_id,
                dietary_preference=DietaryPreference(result['dietary_preference']),
                allergies=allergies,
                dislikes=dislikes,
                daily_calorie_goal=result['daily_calorie_goal'],
                daily_budget=result['daily_budget'],
                preferred_cuisines=preferred_cuisines
            )
            
        except Exception as e:
            logger.error(f"Error getting dietary profile: {e}")
            return None
    
    async def update_dietary_profile(self, profile: UserDietaryProfile) -> bool:
        """Update user's dietary profile"""
        try:
            import json
            
            query = """
            INSERT OR REPLACE INTO dietary_profiles 
            (user_id, dietary_preference, allergies, dislikes, daily_calorie_goal, daily_budget, preferred_cuisines, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            return await self.db.execute_query(
                query,
                (
                    profile.user_id,
                    profile.dietary_preference.value,
                    json.dumps(profile.allergies),
                    json.dumps(profile.dislikes),
                    profile.daily_calorie_goal,
                    profile.daily_budget,
                    json.dumps(profile.preferred_cuisines),
                    datetime.now().isoformat()
                )
            )
            
        except Exception as e:
            logger.error(f"Error updating dietary profile: {e}")
            return False
    
    async def get_meal_suggestions(self, user_id: int, meal_type: MealType, 
                                 budget_limit: Optional[float] = None) -> List[MealItem]:
        """Get meal suggestions for a user"""
        try:
            profile = await self.get_dietary_profile(user_id)
            suggestions = []
            
            # Get multiple recommendations
            for _ in range(5):  # Get up to 5 suggestions
                meal = await self._recommend_meal(meal_type, profile, budget_limit)
                if meal and meal not in suggestions:
                    suggestions.append(meal)
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting meal suggestions: {e}")
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """Service health check"""
        try:
            # Test database connection
            test_query = "SELECT COUNT(*) as count FROM meal_plans LIMIT 1"
            result = await self.db.fetch_one(test_query)
            
            return {
                "status": "healthy",
                "database_connection": "ok",
                "total_meal_plans": result['count'] if result else 0,
                "meal_database_size": sum(len(items) for items in self.meal_database.values()),
                "ai_recommender_available": self.ai_recommender is not None,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
