#!/usr/bin/env python3
"""
My TSI Service - Integration with my.tsi.lv student portal
Provides access to grades, finances, personal info and more
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
import logging
import re
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MyTSIService:
    """Service for interacting with my.tsi.lv student portal"""
    
    BASE_URL = "https://my.tsi.lv"
    LOGIN_URL = f"{BASE_URL}/login"
    LOGOUT_URL = f"{BASE_URL}/logout"
    
    # Main pages
    DASHBOARD_URL = f"{BASE_URL}/dashboard"
    PERSONAL_URL = f"{BASE_URL}/personal"
    STUDY_URL = f"{BASE_URL}/study"
    SCHEDULE_URL = f"{BASE_URL}/schedule"
    BILLS_URL = f"{BASE_URL}/bills"
    CONTRACTS_URL = f"{BASE_URL}/contracts"
    APPLICATIONS_URL = f"{BASE_URL}/applications"
    
    def __init__(self, username: str = None, password: str = None):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        self._is_authenticated = False
        self._student_info: Dict = {}
    
    def login(self, username: str = None, password: str = None) -> bool:
        """Authenticate with my.tsi.lv portal"""
        username = username or self.username
        password = password or self.password
        
        if not username or not password:
            raise ValueError("Username and password are required")
        
        try:
            # Get login page first to establish session
            resp = self.session.get(self.LOGIN_URL)
            
            # Submit login form (no CSRF token needed based on page analysis)
            login_data = {
                "username": username,
                "password": password,
            }
            
            headers = {
                "Referer": self.LOGIN_URL,
                "Origin": self.BASE_URL,
                "Content-Type": "application/x-www-form-urlencoded",
            }
            
            resp = self.session.post(
                self.LOGIN_URL, 
                data=login_data, 
                headers=headers, 
                allow_redirects=True
            )
            
            # Enhanced validation to prevent accepting wrong passwords
            response_text = resp.text.lower()
            
            # Step 1: Check for error indicators in multiple languages
            error_keywords = [
                'invalid', 'incorrect', 'wrong', 'error', 'failed',  # English
                'neveiksmīgs', 'kļūda', 'nepareiz', 'nav derīgs'  # Latvian
            ]
            if any(error in response_text for error in error_keywords):
                logger.error("MyTSI login failed - error detected in response")
                return False
            
            # Step 2: Check for success indicators
            has_logout = "logout" in response_text
            has_dashboard = "/dashboard" in resp.url or resp.url != self.LOGIN_URL
            has_atteikties = "atteikties" in response_text  # Latvian for logout
            
            if not (has_logout or has_dashboard or has_atteikties):
                logger.error("MyTSI login failed - no success indicators found")
                return False
            
            # Step 3: Parse HTML for error messages
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            error = soup.find(class_="error")
            if error and error.get_text(strip=True):
                logger.error(f"MyTSI login error: {error.get_text(strip=True)}")
                return False
            
            # All checks passed
            self._is_authenticated = True
            self.username = username
            self.password = password
            logger.info(f"MyTSI login successful for {username}")
            return True
            
        except Exception as e:
            logger.error(f"MyTSI login error: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return self._is_authenticated
    
    def logout(self):
        """Logout from portal"""
        try:
            self.session.get(self.LOGOUT_URL)
        except:
            pass
        self._is_authenticated = False
        self.session = requests.Session()
    
    def close(self):
        """Close session"""
        self.logout()
    
    def get_dashboard(self) -> Dict[str, Any]:
        """Get dashboard overview - redirects to get_profile for actual data"""
        return self.get_profile()
    
    def get_profile(self) -> Dict[str, Any]:
        """Get student profile/personal information"""
        if not self._is_authenticated:
            return {"error": "Not authenticated"}
        
        try:
            resp = self.session.get(self.PERSONAL_URL)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            profile = {
                "name": "",
                "student_code": "",
                "country": "",
                "personal_code": "",
                "status": "",
                "faculty": "",
                "programme": "",
                "specialization": "",
                "level": "",
                "year": "",
                "study_mode": "",
                "group": ""
            }
            
            # Parse the text content
            text = soup.get_text(separator='|', strip=True)
            
            # Extract fields using patterns
            patterns = {
                "name": r"Name\s*\|\s*([^|]+)",
                "student_code": r"Student code\s*\|\s*(\d+)",
                "country": r"Country\s*\|\s*([^|]+)",
                "personal_code": r"Personal code\s*\|\s*([^|]+)",
                "status": r"Status\s*\|\s*([^|]+)",
                "faculty": r"Faculty\s*\|\s*([^|]+)",
                "programme": r"Programme\s*\|\s*([^|]+)",
                "specialization": r"Specialization\s*\|\s*([^|]+)",
                "level": r"Level\s*\|\s*([^|]+)",
                "year": r"Year of study\s*\|\s*(\d+)",
                "study_mode": r"Study mode\s*\|\s*([^|]+)",
                "group": r"Group\s*\|\s*([^|]+)"
            }
            
            for field, pattern in patterns.items():
                match = re.search(pattern, text, re.I)
                if match:
                    profile[field] = match.group(1).strip()
            
            return profile
            
        except Exception as e:
            logger.error(f"Error fetching profile: {e}")
            return {"error": str(e)}
    
    def get_grades(self) -> List[Dict[str, Any]]:
        """Get student grades/marks"""
        if not self._is_authenticated:
            return []
        
        try:
            resp = self.session.get(self.STUDY_URL)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            grades = []
            current_semester = ""
            
            # Find the main grades table (usually the second one with actual data)
            tables = soup.find_all("table")
            
            for table in tables:
                rows = table.find_all("tr")
                
                for row in rows:
                    cells = row.find_all(["th", "td"])
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    
                    # Check for semester header - look for rows with colspan or single cell with semester info
                    # Semester headers typically: "1 Semester", "2 Semester", etc. or with year
                    if len(cells) >= 1:
                        first_cell = cells[0]
                        first_text = first_cell.get_text(strip=True)
                        
                        # Check if it's a semester header (colspan or merged cell)
                        colspan = first_cell.get('colspan')
                        
                        # Match patterns like "1 Semester", "2 Semester", "Semester 1", "1. Semester 2023/2024"
                        semester_match = re.search(r'(\d+)\s*\.?\s*[Ss]emester|[Ss]emester\s*(\d+)', first_text)
                        if semester_match:
                            # Extract semester number and any year info
                            sem_num = semester_match.group(1) or semester_match.group(2)
                            # Look for year pattern like 2023/2024
                            year_match = re.search(r'(\d{4}/\d{4}|\d{4})', first_text)
                            if year_match:
                                current_semester = f"Семестр {sem_num} ({year_match.group(1)})"
                            else:
                                current_semester = f"Семестр {sem_num}"
                            continue
                    
                    # Skip header rows
                    if any(h in cell_texts for h in ["Subject", "Nr", "Nr.", "Priekšmets", "Grade", "Mark"]):
                        continue
                    
                    # Parse grade row (expect: Nr, Subject, Block, Part, Credit, Grade, Date, Type, Lecturer, ...)
                    if len(cell_texts) >= 6:
                        try:
                            # Check if first cell is a number (Nr)
                            nr = cell_texts[0]
                            if nr.isdigit():
                                grade_entry = {
                                    "semester": current_semester if current_semester else "Без семестра",
                                    "subject": cell_texts[1] if len(cell_texts) > 1 else "",
                                    "credits": cell_texts[4] if len(cell_texts) > 4 else "",
                                    "grade": cell_texts[5] if len(cell_texts) > 5 else "",
                                    "date": cell_texts[6] if len(cell_texts) > 6 else "",
                                    "type": cell_texts[7] if len(cell_texts) > 7 else "",
                                    "lecturer": cell_texts[8] if len(cell_texts) > 8 else ""
                                }
                                if grade_entry["subject"] and grade_entry["grade"]:
                                    grades.append(grade_entry)
                        except (IndexError, ValueError):
                            continue
            
            return grades
            
        except Exception as e:
            logger.error(f"Error fetching grades: {e}")
            return []
    
    def get_bills(self) -> Dict[str, Any]:
        """Get financial information (bills and payments)"""
        if not self._is_authenticated:
            return {"error": "Not authenticated"}
        
        try:
            resp = self.session.get(self.BILLS_URL)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            result = {
                "bills": [],
                "total_paid": 0.0,
                "total_unpaid": 0.0,
                "summary": ""
            }
            
            # Parse the text to find bill entries
            text = soup.get_text()
            
            # Find table rows with bill data
            tables = soup.find_all("table")
            
            for table in tables:
                rows = table.find_all("tr")
                
                for row in rows:
                    cells = row.find_all(["td"])
                    if len(cells) >= 5:
                        cell_texts = [cell.get_text(strip=True) for cell in cells]
                        
                        # Try to parse date (first column usually)
                        date_match = re.match(r'\d{2}\.\d{2}\.\d{4}', cell_texts[0])
                        if date_match:
                            bill = {
                                "date": cell_texts[0],
                                "number": cell_texts[1] if len(cell_texts) > 1 else "",
                                "service": cell_texts[2] if len(cell_texts) > 2 else "",
                                "amount": 0.0,
                                "currency": "EUR",
                                "paid": False,
                                "payment_date": ""
                            }
                            
                            # Find amount (look for number with decimal)
                            for i, text in enumerate(cell_texts):
                                amount_match = re.search(r'(-?\d+\.?\d*)', text.replace(',', '.'))
                                if amount_match and i >= 3:
                                    try:
                                        bill["amount"] = float(amount_match.group(1))
                                    except:
                                        pass
                                
                                # Check for paid status (✔ symbol or date in last columns)
                                if "✔" in text or (re.match(r'\d{2}\.\d{2}\.\d{4}', text) and i > 5):
                                    bill["paid"] = True
                                    if re.match(r'\d{2}\.\d{2}\.\d{4}', text):
                                        bill["payment_date"] = text
                            
                            if bill["amount"] != 0:
                                result["bills"].append(bill)
                                if bill["paid"]:
                                    result["total_paid"] += abs(bill["amount"])
                                else:
                                    result["total_unpaid"] += bill["amount"]
            
            # Create summary
            result["summary"] = f"Оплачено: {result['total_paid']:.2f} EUR"
            if result["total_unpaid"] > 0:
                result["summary"] += f", К оплате: {result['total_unpaid']:.2f} EUR"
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching bills: {e}")
            return {"error": str(e)}
    
    def get_current_semester_grades(self) -> List[Dict[str, Any]]:
        """Get only current semester grades"""
        all_grades = self.get_grades()
        if not all_grades:
            return []
        
        # Find the highest semester number
        semesters = set()
        for g in all_grades:
            sem = g.get("semester", "")
            match = re.search(r'(\d+)', sem)
            if match:
                semesters.add(int(match.group(1)))
        
        if not semesters:
            return all_grades
        
        current_sem = max(semesters)
        return [g for g in all_grades if str(current_sem) in g.get("semester", "")]
    
    def get_gpa(self) -> float:
        """Calculate GPA from all grades"""
        grades = self.get_grades()
        if not grades:
            return 0.0
        
        total_credits = 0
        weighted_sum = 0
        
        for g in grades:
            try:
                # Extract numeric grade
                grade_str = str(g.get("grade", "0")).strip()
                # Remove any non-digit characters but keep the number
                grade_match = re.search(r'(\d+)', grade_str)
                if not grade_match:
                    continue
                grade = int(grade_match.group(1))
                
                # Extract numeric credits
                credits_str = str(g.get("credits", "0")).strip()
                credits_match = re.search(r'(\d+)', credits_str)
                if not credits_match:
                    continue
                credits = int(credits_match.group(1))
                
                if grade > 0 and credits > 0:
                    weighted_sum += grade * credits
                    total_credits += credits
            except (ValueError, TypeError):
                continue
        
        return round(weighted_sum / total_credits, 2) if total_credits > 0 else 0.0
    
    def get_attendance(self) -> Dict[str, Any]:
        """Get attendance data from dashboard"""
        if not self._is_authenticated:
            return {"error": "Not authenticated"}
        
        try:
            resp = self.session.get(self.DASHBOARD_URL)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Get text content
            body = soup.find('body')
            for tag in body.find_all(['script', 'style', 'nav']):
                tag.decompose()
            
            text = body.get_text(separator='\n', strip=True)
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            result = {
                "overall": 0,
                "subjects": [],
                "period": ""
            }
            
            in_attendance = False
            
            for i, line in enumerate(lines):
                # Find attendance section
                if line == "Attendance":
                    in_attendance = True
                    continue
                
                if in_attendance:
                    # Overall percentage (just a number with %)
                    match = re.match(r'^(\d+)%$', line)
                    if match:
                        result["overall"] = int(match.group(1))
                        continue
                    
                    # Subject attendance: "Subject Name - X%"
                    match = re.match(r'^(.+?)\s*-\s*(\d+)%$', line)
                    if match:
                        result["subjects"].append({
                            "subject": match.group(1).strip(),
                            "percentage": int(match.group(2))
                        })
                        continue
                    
                    # Date range
                    date_match = re.match(r'^\d{2}\.\d{2}\.\d{4}\s*-\s*\d{2}\.\d{2}\.\d{4}$', line)
                    if date_match:
                        result["period"] = line
                        continue
                    
                    # End of attendance section (when we hit something else)
                    if not line.startswith("0%") and "%" not in line and result["subjects"]:
                        break
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching attendance: {e}")
            return {"error": str(e)}
    
    def get_dashboard_info(self) -> Dict[str, Any]:
        """Get full dashboard info including credits, debts, attendance"""
        if not self._is_authenticated:
            return {"error": "Not authenticated"}
        
        try:
            resp = self.session.get(self.DASHBOARD_URL)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            body = soup.find('body')
            for tag in body.find_all(['script', 'style', 'nav']):
                tag.decompose()
            
            text = body.get_text(separator='\n', strip=True)
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            result = {
                "credits": {
                    "required": 0,
                    "completed": 0,
                    "remaining": 0
                },
                "debts": {
                    "academic": "No debt",
                    "financial": "No debt",
                    "fines": "No debt",
                    "library": "No debt"
                },
                "attendance": self.get_attendance()
            }
            
            for i, line in enumerate(lines):
                # Credits
                if "Required credits" in line and i+1 < len(lines):
                    try:
                        result["credits"]["required"] = int(lines[i+1])
                    except ValueError:
                        pass
                if "Completed credits" in line and i+1 < len(lines):
                    try:
                        result["credits"]["completed"] = int(lines[i+1])
                    except ValueError:
                        pass
                if "Remaining credits" in line and i+1 < len(lines):
                    try:
                        result["credits"]["remaining"] = int(lines[i+1])
                    except ValueError:
                        pass
                
                # Debts
                if "Academic debts" in line and i+1 < len(lines):
                    result["debts"]["academic"] = lines[i+1]
                if "Financial debts" in line and i+1 < len(lines):
                    result["debts"]["financial"] = lines[i+1]
                if "Debts on fines" in line and i+1 < len(lines):
                    result["debts"]["fines"] = lines[i+1]
                if "Library debts" in line and i+1 < len(lines):
                    result["debts"]["library"] = lines[i+1]
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching dashboard info: {e}")
            return {"error": str(e)}


# Testing function
def test_my_tsi(username: str, password: str):
    """Test MyTSI service"""
    service = MyTSIService()
    
    print("Logging in...")
    if service.login(username, password):
        print("✅ Login successful!")
        
        print("\n👤 Profile:")
        profile = service.get_profile()
        for key, value in profile.items():
            if value:
                print(f"  {key}: {value}")
        
        print("\n📝 Grades:")
        grades = service.get_grades()
        print(f"  Total: {len(grades)} subjects")
        for g in grades[:5]:
            print(f"  - {g['subject']}: {g['grade']} ({g['credits']} credits)")
        
        print(f"\n📊 GPA: {service.get_gpa()}")
        
        print("\n💰 Bills:")
        bills = service.get_bills()
        print(f"  {bills.get('summary', 'No data')}")
        print(f"  Total bills: {len(bills.get('bills', []))}")
        for bill in bills.get("bills", [])[-3:]:
            status = "✅" if bill["paid"] else "⏳"
            print(f"  {status} {bill['date']}: {bill['service'][:30]} - {bill['amount']} EUR")
        
        service.close()
    else:
        print("❌ Login failed!")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        test_my_tsi(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python my_tsi_service.py <username> <password>")
