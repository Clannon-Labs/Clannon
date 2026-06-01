from abc import ABC, abstractmethod
from typing import Any, Dict, List

class BaseMemoryLayer(ABC):
    """
    Abstract Base Class for all Vraksha Memory Layers.
    
    This interface ensures that all storage components (Wiki, Semantic, Graph) 
    adhere to a consistent contract for ingestion and retrieval, allowing the 
    MemoryCoordinator to orchestrate them polymorphically.
    """

    @abstractmethod
    def add(self, content: Any, **kwargs) -> bool:
        """
        Insert new content into the memory layer.
        Must return True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve relevant memory based on a query.
        Must return a list of dictionaries, where each dict represents a retrieved memory item.
        """
        pass

    @abstractmethod
    def get_essential_context(self) -> str:
        """
        Retrieve context that MUST be injected into every agent prompt.
        If the memory layer doesn't hold essential, prompt-injected context, it can return an empty string.
        """
        pass
