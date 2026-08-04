from typing import Optional, Dict, Any
from aiogram.fsm.context import FSMContext

MAX_HISTORY = 30  # Xotirani tejash va ortiqcha yuklamani oldini olish uchun limit

class NavigationManager:
    def __init__(self, state: FSMContext):
        self.state = state

    async def push(self, page_name: str, **kwargs) -> None:
        data = await self.state.get_data()
        history: list = data.get("nav_history", [])
        
        current_step = {"page": page_name, "params": kwargs}
        
        # 1. Agar oxirgi sahifa ham xuddi shu bo'lsa (masalan: favorites -> favorites), qayta qo'shmaymiz
        if history and history[-1]["page"] == page_name:
            history[-1] = current_step
        else:
            # 2. HALQANI (LOOP) KESISH:
            # Agar qo'shilayotgan sahifa tarixdan allaqachon bo'lsa (masalan cabinet -> favorites -> cabinet),
            # o'sha sahifadan keyingi barcha zanjirni kesib tashlaymiz!
            found_index = None
            for i, step in enumerate(history):
                if step["page"] == page_name:
                    found_index = i
                    break
            
            if found_index is not None:
                # Topilgan joygacha bo'lgan tarixni saqlaymiz va joriy parametrlar bilan yangilaymiz
                history = history[:found_index]
            
            history.append(current_step)
            
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]
            
        await self.state.update_data(nav_history=history)

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