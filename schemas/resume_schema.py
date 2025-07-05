from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import date

class Education(BaseModel):
    institution: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None
    achievements: Optional[List[str]] = []

class Experience(BaseModel):
    company: str
    position: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None
    technologies: List[str] = []

class Project(BaseModel):
    name: str
    description: Optional[str] = None
    technologies: List[str] = []

class Resume(BaseModel):
    contact: Optional[Dict] = {}
    summary: Optional[str] = None
    skills: List[str] = []
    education: List[Education] = []
    experience: List[Experience] = []
    projects: List[Project] = []
    certifications: List[str] = []