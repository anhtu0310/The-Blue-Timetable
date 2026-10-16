# The Blue Time Table 


## Project summary
The Blue Time Table is a web dashboard that helps coordinate teacher/volunteer and students at Blue Dragon Learning and Development department. Where the administrator (HangKM) assign, create classes, assign teachers, and student, assign study room and timeline. The teachers also use this dashboard with a teacher/staff account to check schedule, attendance check, evaluate the study session.


## Project requirement 
### System requirement

#### Teachers and Students Profile

Teacher profile contains following information:
- Teacher name 
- DOB
- Phone number
- Role (teacher or Volunteer)
- Current job
- Teaching subjects (subject tags)
- Assigned classes


Student profile contains following information:
- Student name 
- DOB
- Social worker name
- Social worker phone number 
- Interested subjects (subject tags)
- Assigned classes
- Student attendances
- Class session feedback by teacher

The subject tags (Teaching/Interested subjects) shall be designed as tags where it can help to match students with teachers, and easily find students/teachers when creating the classes.  

Moderator/Admin can search and filter students/teacher by tags name, when searching by tags the search world does not has to match the tag fully 

#### Classes
The classes shall contain the following information:
- Class subject 
- Schedule, when is it happens 
- Frequency, how often does the class occur ? weekly, bi-weekly, or certain day
- Class status (On going, Paused, Ended)
- Assigned Teacher
- Assigned Student  (maximum 10 per class)
- Location (room number)
- Class change history
- Class sessions attendance
- Class session change history
- Class material

Class numbers:
- The class number shall has 2 letters prefix represent the class subject in VNese
- The next 2 numbers are the subject grade
- The last 2 numbers are just class number count from 0 - 99  

Each class sessions will has following functions :
- Attendance check for students
- Feedback for each students by the teacher 
- Once submit, after 24hrs teacher can no longer update that session information   

Session deviation:
- If teacher can take the class, or class need to reschedule then moderators can use this function to change the session information once for that session.  


#### Dashboard account types
There are two kind of account in the Dashboard
- Administration Account
- Moderator Accounts
- Teacher/volunteer Accounts

Only teachers have accounts, students only have profile contains their information  

The Teacher/volunteer Accounts will have following permissions and properties:
- View their own profile, contains their specialties, subjects that they can teach
- Check the assigned class and personal schedule
- View the profile of the student that were assigned to their class
- Attendance check, and comment on the class/session (within 24hr of the class schedule) 


The Moderator Accounts will have following permissions and properties:
- All properties of the Teacher account
- Create classes, modify classes information, including schedule, teachers, students and room number.
- Assign class to students and teachers
- View the profile of all teachers (including other moderators) and all students
- Any teacher account can be assigned as moderator by the Administrator

The Administration Accounts will have all permissions and properties of other account:
- All properties of the Teacher account and moderator account
- Create/modify/delete profile of any students, any account (including profile) of teachers and moderators
- Assign Moderator and admin role for other account.


### UI/UX Requirement

#### UI Language 
Vietnamese

English (not needed in the few first builds, might need to be added later)

### Log in UI
Provide a standard login UI

### Dashboad UI
Dasboard UI will contains different tabs, one tab will contains a month calendar will all of the class in the month , it show the class which that account allow to see, and when click on a class , all class information show up in a pop-up. IF that account has permission to edit the class then it can be edited on the same pop-up

### Security Requirement
Implement a simple login and account security , this can be study and update later 