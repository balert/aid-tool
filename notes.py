import os 

class Notes():
    
    def __init__(self, filename):
        self.filename = filename
        if os.path.exists(filename):
            with open(filename, "r") as f:
                self.notes = f.readlines()
        else: 
            self.notes = []
    
    def get(self, fid):
        try:
            note = next(n for n in self.notes if n.startswith(fid))
            return note.strip().split("|", 1)[1] 
        except StopIteration:
            return ""
    
    def insert(self, fid):
        if not any(s.startswith(fid) for s in self.notes):
            self.notes.append("%s| \n" % fid)
        
    def write(self):
        self.notes.sort()
        with open(self.filename, "w") as f:
            f.writelines(self.notes)