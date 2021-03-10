
# Kafka Database Streaming

This project demonstrates how one can use a Kafka cluster to set up a streaming service from a relational database (MySQL) into a another relational DB (Postgres), noSQL DB (MongoDB) and S3 bucket. This allows you to read once using Kafka's JDBC Source Connector to populate a Kafka Topic per table which can be propogated to other applications and systems. Kafka is the perfect solution for a low latency, real time solution.

We will use the JDBC Source and Sink connectors that are availablce at confluent hub in order to create our producers and consumers from the relational databases.

## Set up secret ENV variables

Add your own S3 variables to a new file named .env in the root of this directory.

AWS_ACCESS_KEY_ID=<ENTER YOUR ACCESS KEY ID>
AWS_SECRET_ACCESS_KEY=<ENTER YOUR ACCESS KEY>

Run `set -a`
Load your env variables `source .env`

## Begin all Services

`docker-compose up -d`

- Zookeeper (confluent): This keeps everything ticking together
- Schema Registry (confluent)
- Kafka (confluent): This is our broker
- Kafka-connect (confluent): The connector API, end point where we configure connections to kafka
- Kafdrop : Monitors the cluster in a simple UI

- MySQL 8 (source)
- PostGres (target)
- MongoDB (target)


# Installing further connectors

One of the important learning point is understanding how to download additional connectors from the confluent hub or a 3rd party (debezium). These must be downloaded into our kafka-connect serivce. The Mongo and Redshift connectors are both examples of these. I am using the docker-compose command in order to download these upon deployment.

Here is the snippet from our docker-compose.yml

```
command: 
      - /bin/bash
      - -c 
      - |
        confluent-hub install --no-prompt confluentinc/kafka-connect-aws-redshift:latest
        confluent-hub install --no-prompt mongodb/kafka-connect-mongodb:latest
        # MySQL
        cd /usr/share/java/kafka-connect-jdbc/
        curl https://repo1.maven.org/maven2/mysql/mysql-connector-java/8.0.20/mysql-connector-java-8.0.20.jar --output mysql-connector-java-8.0.20.jar 

        cd /usr/share/confluent-hub-components/confluentinc-kafka-connect-aws-redshift/lib
        curl https://s3.amazonaws.com/redshift-downloads/drivers/jdbc/1.2.43.1067/RedshiftJDBC42-1.2.43.1067.jar --output RedshiftJDBC42-1.2.43.1067.jar
        # Now launch Kafka Connect
        sleep infinity &
        /etc/confluent/docker/run 
```

## Configure source connector (incremental and update)

There are two types of connectors in Kafka; Source and Sink. We will first configure our source connector to read from our source database (MySQL) into our kafka broker. Run the following command once all services are up and running (usually takes 2 minutes)

```
  curl -X POST \
  -H "Content-Type: application/json" \
  --data '{ "name": "mysql_source", 
            "config": { 
                  "connector.class": "io.confluent.connect.jdbc.JdbcSourceConnector", 
                  "tasks.max": 1, 
                  "connection.url": "jdbc:mysql://mysql:3306/source", 
                  "connection.user": "root", 
                  "connection.password": "Admin123", 
                  "mode": "timestamp+incrementing", 
                  "incrementing.column.name": "id",
                  "timestamp.column.name": "updated_at", 
                  "catalog.pattern":"source",
                  "topic.prefix": "mysql-source-", 
                  "poll.interval.ms": 1000 } }' \
  http://localhost:8083/connectors

```

In our docker-compose MySQL service bash script we have already added one table `source.first_table` as an example. Our kafka broker will pick up this table as our first topic thanks to the property included: `"catalog.pattern":"source"` and will name the topic: `mysql-source-first_table` thanks to the property: "topic.prefix": "mysql-source-". 

We have chosen the mode timestamp + incremental so both updates to existing rows and new rows are upserted. It is important that your incrementing (id) and timstamp column (updated_at) are explicitlyy 'default not null' or else this connector will fail.

### Check the connector status

use jq to beautify your responses. This will need to be downloaded if not already on your system. Mac users can use `brew install jq`.

**Check plugins** : `curl localhost:8083/connector-plugins | jq`  
This should show our mongo and redshift connectors that are downloaded from the confluent hub in the initial commmand in our docker-compose. These are saved to '/usr/share/confluent-hub-components'  and '/usr/local/share/kafka/plugins' which are added to our connect_plugin_path so Kafka knows where to look for plugins. The JDBC plugin comes by default with the confluent platform (cp-kafka-connect). One can easily install salesforce source/sink connectors from confluent hub and many others.

**Status of connector**: `curl -s -X GET http://localhost:8083/connectors/mysql_source/status | jq`

**Use Kafdrop to Monitor your cluster**
open http://localhost:9000/. This is an open source UI built to connect kafka and kafka connect in one simple ui. It shows all the topics and consumers / producers. Load the messages by navigating to our topic [mysql-source-first_table](http://localhost:9000/topic/mysql-source-first_table/). Use Avro formatting to read our messages correctly.

**Read topic** docker-compose run --rm kafka kafka-console-consumer --bootstrap-server kafka:29092  --topic mysql-source-first_table --from-beginning

This will show strange characters as we have opted to use Avro formatting. But it is useful to debug.


## Configure Sink JDBC Connector

Now we are happy that we are populating messages within our kafka cluster let's go ahead and set up a Sink connector to Postgres. 

Using our docker instance of Postgres and the JDBC sink connector we can run the following command:

```
curl -X POST http://localhost:8083/connectors -H "Content-Type: application/json" \
   -d '{ 
        "name": "sink-pg",
        "config": {
            "connector.class":"io.confluent.connect.jdbc.JdbcSinkConnector",
            "tasks.max":1,
            "connection.url":"jdbc:postgresql://postgres:5432/target",
            "connection.user":"admin",
            "connection.password":"password",
            "poll.interval.ms":"1000",
            "table.name.format": "${topic}",
            "topics.regex":"mysql-source-(.*)",
            "insert.mode":"upsert",
            "pk.mode":"record_value",
            "pk.fields":"id",
            "auto.create":"true",
            "auto.evolve":"true",
            "batch.size": 3000
        }
        }'
```
### Check the sink connector status

Check the status: `curl -s -X GET http://localhost:8083/connectors/sink-pg/status | jq`

To update config use a PUT request against the Kafka REST API as follows:

Increase poll interval to five minutes to batch load into our source instead of live streaming.

```
  curl -X PUT -H "Content-Type: application/json" \
  --data '{ "poll.interval.ms": 300000 }' \
  http://localhost:8083/connectors/sink-pg/config
```

I usually open the postgres database on my pSQL client to check that the data is flowing in but you can use the CLI too by accessing `docker exec -it kafka-mysql psql -uadmin -p`.


## Add a second source table

To prove that our Source connector will auto generate topics for each table within our mysql 'source' database we will add another table `source.second_table`.

Run `docker exec -it kafka-mysql mysql -uroot -p`

Enter password set up in docker-compose.yml: Admin123

Once open run the following SQL script:

```
CREATE TABLE source.second_table
        (
            id            int(11) PRIMARY KEY AUTO_INCREMENT NOT NULL,
            name  varchar(100) NOT NULL,
            date_field    date NOT NULL,
            decimal_field decimal(18, 5) NOT NULL,
            created_at    datetime DEFAULT CURRENT_TIMESTAMP,
            updated_at    datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL
        );

INSERT INTO source.second_table(name, date_field, decimal_field)
        VALUES ('rupert', '2020-01-01', 12345),
               ('toby', '2020-01-02', 12346.12),
               ('nick', '2020-01-03', 12345.12),
               ('james', '2020-01-04', 12345.123),
               ('jamie', '2020-01-05', 12345.2454);
```

## Show that schema changes are picked up in the Avro Messages

Run your docker mysql instance if you haven't already: `docker exec -it kafka-mysql mysql -uroot -p`

Now run the following SQL statement:
```
ALTER TABLE source.first_table 
ADD COLUMN additional_column varchar(100);

UPDATE TABLE source.first_table 
SET additional_column = 1 WHERE additional_column IS NULL;
```

Run `ctrl+d` to quit mysql terminal

Check in your Postgres target database and your Kafka broker (using Kafdrop) to check the schema changes have been reflected correctly. 


### Simulate a data stream

To simulate a real application, I use a data generator to load fake data into our mysql source table.

1. If not already installed: `pip3 install virtualenv`
2. Set up py env: `virtualenv pyenv`
3. Load all requirements: `pip3 install -r requirements.txt`
4. Activate env:`source pyenv/bin/activate`
5. Beging loading`python3 generate_data.py`

This will start loading data every second into our source.first_table. Check kafdrop to ensure this is happening.
You should see the data instantly load into your source and target databases.


### Set up Mongo DB sink

Mongo is a useful noSQL database storage. Ideal for applications that are growing rapidly where a schema would be too restrictive. We will use our docker mongo service; kafka-mongo for this demonstration.

We use the avro converter to ensure that mongo can read the Avro formated topics.

execute the following API request to create our mongo sink connector.
```
curl -X PUT http://localhost:8083/connectors/sink-mongodb/config -H "Content-Type: application/json" -d ' {
        "connector.class":"com.mongodb.kafka.connect.MongoSinkConnector",
        "tasks.max":"1",
        "topics":"mysql-source-first_table",
        "connection.uri":"mongodb://root:rootpassword@mongodb:27017",
        "database":"kafka-test",
        "collection":"dev",
        "key.converter":"io.confluent.connect.avro.AvroConverter",
        "key.converter.schema.registry.url":"http://schema-registry:8081",
        "key.converter.schemas.enable":false,
        "value.converter":"io.confluent.connect.avro.AvroConverter",
        "value.converter.schema.registry.url":"http://schema-registry:8081"
}'   
```

To check this has loaded:

1. Load Docker Mongo shell ` docker exec -it kafka-mongo mongo --username root --password rootpassword --authenticationDatabase admin `
2. Switch to the kafka db ` use kafka-test `
3. Read all from 'dev' collection ` db.dev.find() `

This should play back all messages from the topic: mysql-source-first_table 

4. `ctrl+d` to quit


### Set up S3 Sink

Finally, to write data to S3 it is pretty straight forward too. You will need to setup environment variables: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in the `docker-compose-kafka.yml` file. After that you can create a S3 connector using the following configs:

```
curl -i -X PUT -H "Accept:application/json" \
    -H  "Content-Type:application/json" http://localhost:8083/connectors/sink_s3/config \
    -d '
{
    "connector.class": "io.confluent.connect.s3.S3SinkConnector",
    "s3.region": "eu-west-1",
    "s3.bucket.name": "li-kafka-lake",
    "topics": "mysql-source-first_table",
    "flush.size": "5",
    "timezone": "UTC",
    "tasks.max": "1",
    "value.converter.value.subject.name.strategy": "io.confluent.kafka.serializers.subject.RecordNameStrategy",
    "locale": "US",
    "format.class": "io.confluent.connect.s3.format.json.JsonFormat",
    "partitioner.class": "io.confluent.connect.storage.partitioner.DefaultPartitioner",
    "internal.value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "storage.class": "io.confluent.connect.s3.storage.S3Storage",
    "rotate.schedule.interval.ms": "6000"
}'
```
Some notable properties:
- `s3.region`: the region of the s3 bucket
- `s3.bucket.name`: bucket name to write to
- `topics`: kafka topic to read from
- `format.class`: data format. You can choose from `JSON`, `Avro` and `Parquet`


So there it is, all the infrastructure needed to locally manage a Kafka cluster. This can all be scaled horizontally and other services can be used such as Ksql to enhance Kafka. I will explore KSQL in my next repo.


### Tear everything down

`docker-compose down` Will end all services in our yml file.

If you want to get rid of all containers to free up space ensure to prune:
`docker system prune`