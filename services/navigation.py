# services/navigation.py
from typing import Optional, Dict, Any
from aiogram.fsm.context import FSMContext

MAX_HISTORY = 30  # Xotirani tejash va ortiqcha yuklamani oldini olish uchun limit
class NavigationManager:
    def __init__(self, state: FSMContext): #[cite: 18]
        self.state = state #[cite: 18]
    async def push(self, page_name: str, **kwargs) -> None: #[cite: 18]
        data = await self.state.get_data() #[cite: 18]
        history: list = data.get("nav_history", []) #[cite: 18]
        
        current_step = {"page": page_name, "params": kwargs} #[cite: 18]
        
        # 1. Agar oxirgi sahifa ham xuddi shu bo'lsa (masalan: favorites -> favorites), qayta qo'shma[cite: 18]
        if history and history[-1]["page"] == page_name:
            # Faqat parametrlarni yangilab qo'yamiz
            history[-1] = current_step
        else:
            history.append(current_step) #[cite: 18]
            
        if len(history) > MAX_HISTORY: #[cite: 18]
            history = history[-MAX_HISTORY:] #[cite: 18]
            
        await self.state.update_data(nav_history=history) #[cite: 18]

    async def pop(self) -> Dict[str, Any]:
        """Orqaga bosilganda joriy sahifani o'chirib, OLDINGI sahifaga qaytaradi."""
        data = await self.state.get_data()
        history: list = data.get("nav_history", [])
        
        if len(history) > 1:
            history.pop()  # Hozirgi o'tirgan sahifamizni o'chiramiz
            previous_step = history[-1]  # Bitta oldingi sahifani olamiz
            await self.state.update_data(nav_history=history)
            return previous_step
        
        # Agar tarix bo'sh bo'lsa yoki 1 ta element bo'lsa -> Bosh menyu
        default_menu = {"page": "main_menu", "params": {}}
        await self.state.update_data(nav_history=[default_menu])
        return default_menu

    async def clear(self) -> None:
        """/start yoki Bosh menyuga qaytganda tarixni tozalash."""
        await self.state.update_data(nav_history=[{"page": "main_menu", "params": {}}])