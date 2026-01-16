from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role
    
    def get_id(self):
        return str(self.id)
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_employee(self):
        return self.role == 'employee'