from multiprocessing import connection
from unittest import removeResult
from flask import Blueprint, jsonify,current_app,request,session
from util.database import Database
from util.response_util import create_error_response
import datetime
from datetime import datetime
#current error that occurs in either in login if the below import is removed(JC)--> will figure out
import datetime
import re,jwt,re,bcrypt



users_blueprint = Blueprint('users', __name__)




@users_blueprint.route('/register', methods=["POST"]) 
@Database.with_connection
def do_register(**kwargs):
    cursor = kwargs["cursor"] 
    connection = kwargs["connection"]
    
    try: 
 #Takes incoming data as json
      incoming_data = request.get_json()
      nid_ = incoming_data['nid']
      password_ = incoming_data['password']
      email_ = incoming_data['email'] 
      #comfirm_Pwrd = incoming_data['Comfirm_pass'] 
#set role and verified automatically to user and Admin and Super admnin or 0 to verified 
      verified_ = 0
      role_ = 'User' 
      
 #If variables were inserted then proceed  
      if nid_ and password_ and email_ and request.method == 'POST': 
        #if password != comfirm_Pwrd:
         #return create_error_response('Passwords do not match!', 404)

        hashed_Password = bcrypt.hashpw(password_.encode('utf-8'), bcrypt.gensalt()) 
 #sql query to check if Email exists already
      
        cursor.execute('SELECT * FROM users WHERE email = %s', (email_,))     
        exist_acc = cursor.fetchone()  
#Check to see if account exist already or not
        if exist_acc:
          return create_error_response('Account already exists!', 404)
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email_): 
          return create_error_response('Invalid email address!', 404)
        else:          
          sqlQuery_2 = "INSERT INTO users(nid, password, email, verified, role) VALUES(%s, %s, %s, %s, %s)"
          data = (nid_, hashed_Password, email_, verified_, role_,)
          cursor.execute(sqlQuery_2, data)
          connection.commit() 
      
          return jsonify({"message": "New account created"})
        
      else:
        return create_error_response('Please enter the required fields!', 404)

    except Exception as err:    
      print(err)
      return create_error_response('Error', 404) 


@users_blueprint.route('/login', methods=["POST"]) 
@Database.with_connection
def do_login(**kwargs): 
  try:
   cursor = kwargs["cursor"] 
   connection = kwargs["connection"] 
   secret_key = kwargs["secret_key"]

#Takes incoming data as json
   incoming_data = request.get_json()
   email_ = incoming_data['Email']
   password_ = incoming_data['Password'] 

   if email_ and password_ and request.method == 'POST':         
#sql query to check if Email exists already
      sqlQuery_1 = "SELECT * FROM users WHERE Email = %s" 
      cursor.execute(sqlQuery_1, (email_,))     
      exist_acc = cursor.fetchone() 
        
      hash_pwrd = exist_acc['password'] 
      userid = exist_acc['ID']  
      
      if exist_acc: 
        if bcrypt.checkpw(password_.encode('utf-8'), hash_pwrd.encode('utf-8')): 
           my_token = jwt.encode({'user_id' : userid, 'exp' : datetime.datetime.utcnow() + datetime.timedelta(minutes=30)}, secret_key) 
 #might need to decode using ('utf-8') ^^ if we do not import datetime we will get an error.
           return jsonify({'token' : my_token})
                 
        else:
               return create_error_response('Password do not match!', 404)
      else:
            return create_error_response('Account does not exist!', 404)
   else:
        return create_error_response('Please enter all required fields!', 404) 
  except Exception as err:
    print(err)
    return create_error_response('Error', 404)      


@users_blueprint.route('/<int:id>', methods=["DELETE"]) 
@Database.with_connection
def do_delete(id,**kwargs):  
  cursor = kwargs["cursor"] 
  connection = kwargs["connection"]
  try:
    id_ = id 
#checks to see if user exist or not
    sqlQuery_1 = "SELECT * FROM users WHERE ID = %s" 
    cursor.execute(sqlQuery_1, (id_,))     
    exist_acc = cursor.fetchone() 

    if not exist_acc:
      return create_error_response('User does not exist', 404) 
  
#sql query to delete user if it exists already
    sqlQuery_2 = "DELETE FROM users WHERE ID=%s"
 
    try:
     cursor.execute("DELETE FROM reservation WHERE user = %s" % (id_,)) 
     cursor.execute(sqlQuery_2 % (id_,)) 
      
     connection.commit() 
    except Exception as err:
      print(err)
      connection.rollback()
      return create_error_response('Error', 404)      
  
    return jsonify({"status": "Success"}) 
  except Exception as err:
      print(err)
      connection.rollback()
      return create_error_response('Error', 404)


@users_blueprint.route('/<int:id>', methods=["GET"]) 
@Database.with_connection
def get_user_byID(id,**kwargs): 
    cursor = kwargs["cursor"] 

    id_ = id 
    
#sql query to check if user exists already
    sqlQuery_1 = "SELECT * FROM users WHERE ID=%s"
    cursor.execute(sqlQuery_1, (id_,)) 
    exist_acc = cursor.fetchone() 
    created_ = exist_acc['created']
    nid_ = exist_acc['nid']
    email_ = exist_acc['email']

    if exist_acc:
      return jsonify({"created" : created_,
                      "nid" : nid_,
                      "email" : email_
      })
    else:
      return create_error_response('User does not exist', 404)
    

  
   
    