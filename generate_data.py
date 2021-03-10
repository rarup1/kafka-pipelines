from faker import Faker
from time import sleep
import random
import decimal
import pandas as pd
from sqlalchemy import create_engine

if __name__ == '__main__':
    conn = create_engine(
                'mysql+mysqlconnector://{username}:{password}@{server}/{database}'.format(
                    username='root',
                    password='Admin123',
                    server='localhost',
                    database='source'
                ))

    faker = Faker() 
    fields = ['name','birthdate']
    i=0

    while i < 1000: 
        data = faker.profile(fields)
        df = pd.DataFrame(data,index=[1])
        df.columns=['name','date_field']
        df['decimal_field'] = float(decimal.Decimal(random.randrange(1, 10000))/100)
        print(f"Inserting data {data}")
        df.to_sql('first_table',conn, if_exists='append', index=False)
        i += 1 
        sleep(5)
