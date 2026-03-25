"""Shared Pydantic models for 58:12 Global Connect CRM"""
from pydantic import BaseModel, ConfigDict
from typing import List, Optional


class UserRegister(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    national_id: Optional[str] = None
    password: str

class UserLogin(BaseModel):
    identifier: str
    password: str

class UserOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    national_id: Optional[str] = None
    role: str = "volunteer"
    status: str = "active"
    created_at: str

class MemberCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    national_id: Optional[str] = None
    role: str = "Staff"
    secondary_roles: Optional[List[str]] = []
    group: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    notes: Optional[str] = None
    location_id: Optional[str] = None
    department: Optional[str] = None
    program: Optional[str] = None
    is_parent: bool = False
    is_customer: bool = False
    is_donor: bool = False
    pin: Optional[str] = None

class MemberUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    national_id: Optional[str] = None
    role: Optional[str] = None
    secondary_roles: Optional[List[str]] = None
    group: Optional[str] = None
    gender: Optional[str] = None
    status: Optional[str] = None
    date_of_birth: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    notes: Optional[str] = None
    location_id: Optional[str] = None
    department: Optional[str] = None
    program: Optional[str] = None
    is_parent: Optional[bool] = None
    is_customer: Optional[bool] = None
    is_donor: Optional[bool] = None
    pin: Optional[str] = None

class FamilyCreate(BaseModel):
    family_name: str
    primary_contact_name: str
    primary_contact_email: Optional[str] = None
    primary_contact_phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    parent_ids: Optional[List[str]] = []
    guardians: Optional[List[dict]] = []

class ChildCreate(BaseModel):
    name: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    family_id: Optional[str] = None
    class_group: Optional[str] = None
    medical_notes: Optional[str] = None
    allergies: Optional[str] = None
    emergency_contact: Optional[str] = None
    notes: Optional[str] = None

class GuestCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    visit_date: Optional[str] = None
    referred_by: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None

class EventCreate(BaseModel):
    title: str
    type: str = "service"
    date: str
    time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    location_id: Optional[str] = None
    venue_id: Optional[str] = None
    capacity: int = 100
    description: Optional[str] = None
    is_public: bool = True
    is_free: bool = True
    price: Optional[float] = None
    visibility: str = "external"
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    recurrence_day: Optional[int] = None
    programme_id: Optional[str] = None

class EventUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    location_id: Optional[str] = None
    venue_id: Optional[str] = None
    capacity: Optional[int] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    is_free: Optional[bool] = None
    price: Optional[float] = None
    visibility: Optional[str] = None
    status: Optional[str] = None
    is_recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None
    recurrence_day: Optional[int] = None

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"
    assignee: Optional[str] = None
    assignees: Optional[List[str]] = []
    due_date: Optional[str] = None
    tags: Optional[List[str]] = []
    labels: Optional[List[dict]] = []
    checklist: Optional[List[dict]] = []
    attachments: Optional[List[dict]] = []
    board_id: Optional[str] = None
    list_id: Optional[str] = None
    list_name: Optional[str] = None
    position: Optional[int] = 0
    is_archived: bool = False


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    assignees: Optional[List[str]] = None
    due_date: Optional[str] = None
    tags: Optional[List[str]] = None
    labels: Optional[List[dict]] = None
    checklist: Optional[List[dict]] = None
    attachments: Optional[List[dict]] = None
    board_id: Optional[str] = None
    list_id: Optional[str] = None
    list_name: Optional[str] = None
    position: Optional[int] = None
    is_archived: Optional[bool] = None

class CheckInCreate(BaseModel):
    member_id: Optional[str] = None
    member_name: str
    type: str = "member"
    event_id: Optional[str] = None
    event_name: Optional[str] = None
    method: str = "manual"
    pin: Optional[str] = None
    location_id: Optional[str] = None

class VenueCreate(BaseModel):
    name: str
    capacity: int
    type: str = "hall"
    description: Optional[str] = None
    hourly_rate: Optional[float] = None
    available: bool = True
    location_id: Optional[str] = None

class VenueUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    type: Optional[str] = None
    description: Optional[str] = None
    hourly_rate: Optional[float] = None
    available: Optional[bool] = None
    location_id: Optional[str] = None

class PublicBookingCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    event_id: str
    num_tickets: int = 1

class SpaceBookingCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    venue_id: str
    booking_date: str
    start_time: str
    end_time: str
    purpose: Optional[str] = None

class AuditLogCreate(BaseModel):
    action: str
    resource: str
    resource_id: Optional[str] = None
    details: Optional[dict] = None
