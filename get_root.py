from pathlib import Path

class ROOT:
    @property
    def project(self) -> Path:
        """
            Search for files/folders like .git, requirements.txt and vraksha markers
            to get the path of the project directory from where the code is being ran
        
            Fallback to None if not found or error
        """

        current = Path(__file__).resolve()

        for parent in [current] + list(current.parents):
            if (parent / ".git").exists() or (parent / "requirements.txt").exists():
                return parent
            
            if parent.name.lower() == "vraksha":
                return parent
        
        return None

    @property
    def system(self) -> Path:
        """
            To get the system root (e.g., '/' or 'C:\\')
            regardless of where the code is being ran
        """
        return self.project.anchor

root = ROOT()