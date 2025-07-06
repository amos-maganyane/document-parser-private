from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel

class Contact(BaseModel):
    """Contact information"""
    name: str
    phone: str
    email: str
    linkedin: str
    github: str

class Experience(BaseModel):
    """Work experience"""
    position: str
    company: str
    location: str
    start_date: str
    end_date: str
    description: str
    technologies: List[str]

class Education(BaseModel):
    """Education information"""
    institution: str
    degree: str
    field_of_study: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: str
    achievements: List[str]

class Project(BaseModel):
    """Project information"""
    position: str
    company: str
    location: str
    start_date: str
    end_date: str
    description: str
    technologies: List[str]

class Resume(BaseModel):
    """Resume model"""
    contact: Contact
    summary: str
    skills: List[str]
    education: List[Education]
    experience: List[Experience]
    projects: List[Project]
    certifications: List[str] 