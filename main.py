from datetime import datetime
import os
from time import sleep
import streamlit as st
import pandas as pd
import json
import streamlit_highcharts as hct
import keboola_api as kb
from snowflake.snowpark import Session

st.set_page_config(layout="wide")



path = os.path.dirname(__file__)
my_file = path+'/img.png'
st.image(my_file, width=102)

connection_parameters = {
    "account": st.secrets['account'].replace('https://','').replace('.snowflakecomputing.com',''),
    "user": st.secrets['user'],
    "password": st.secrets['password'],
    "warehouse": st.secrets['warehouse'],
}

session = Session.builder.configs(connection_parameters).create()  

 
db_name=st.secrets['db_name']
schema_name=st.secrets['schema_name']
keboola_URL="https://connection.north-europe.azure.keboola.com"
keboola_key=st.secrets['keboola_key']

query=f'''
use database {db_name}; 
'''
session.sql(query).collect()
query=f'''
use schema {schema_name}; 
'''
session.sql(query).collect()

buckets=kb.keboola_bucket_list(
                keboola_URL=keboola_URL,
                keboola_key=keboola_key,
                label=" GET BUCKETS",
                api_only=True,
                key="oneone"
        )

def saveFile(df):
    with open(os.path.join(os.getcwd(),str(session.get_current_account().replace('"',''))+'.csv'),"w") as f: 
        f.write(df.to_csv(index=False))
        return os.path.join(os.getcwd(),str(session.get_current_account().replace('"',''))+'.csv')
       

st.markdown("## RFM Segmentation")

def getRevSplit(segment,discount,increase):
    ls=",".join("'{0}'".format(w) for w in segment)
    if ls=="":
        ls="''"
    queryAll=f'''
        SELECT ALLSELL.TYPE,ALLSELL.product_manufacturer as PR, ROUND(sum(ALLSELL.DISC),0) AS REV
        FROM
            (SELECT 'DISC' as TYPE,P.product_manufacturer, O.ORDER_LINE_PRICE_WITH_TAXES as Sales, ((Sales*{1+(increase/100)}) - Sales*{(discount/100)}) as DISC ,O.ORDER_ID, C.CUSTOMER_ID,RF.SEGMENT
                FROM "bdm_order_lines" as O 
                INNER JOIN "bdm_products" as P 
                ON P.PRODUCT_ID=O.ORDER_LINE_PRODUCT_ID
                INNER JOIN "bdm_orders" as OS
                ON O.ORDER_ID=OS.ORDER_ID
                INNER JOIN "bdm_customers" as C
                ON OS.CUSTOMER_ID=C.customer_id
                INNER JOIN "bdm_rfm" as RF
                ON RF.CUSTOMER_ID=C.customer_id WHERE RF.SEGMENT IN ({ls})
            UNION (
                (SELECT 'ALL' as TYPE,P.product_manufacturer, O.ORDER_LINE_PRICE_WITH_TAXES as Sales, Sales as DISC ,O.ORDER_ID, C.CUSTOMER_ID,RF.SEGMENT
                FROM "bdm_order_lines" as O 
                INNER JOIN "bdm_products" as P 
                ON P.PRODUCT_ID=O.ORDER_LINE_PRODUCT_ID
                INNER JOIN "bdm_orders" as OS
                ON O.ORDER_ID=OS.ORDER_ID
                INNER JOIN "bdm_customers" as C
                ON OS.CUSTOMER_ID=C.customer_id
                INNER JOIN "bdm_rfm" as RF
                ON RF.CUSTOMER_ID=C.customer_id WHERE RF.SEGMENT NOT IN ({ls}) )
            UNION(
                SELECT 'EXCEPT' as TYPE,P.product_manufacturer, O.ORDER_LINE_PRICE_WITH_TAXES as Sales, Sales as DISC ,O.ORDER_ID, C.CUSTOMER_ID,RF.SEGMENT
                FROM "bdm_order_lines" as O 
                INNER JOIN "bdm_products" as P 
                ON P.PRODUCT_ID=O.ORDER_LINE_PRODUCT_ID
                INNER JOIN "bdm_orders" as OS
                ON O.ORDER_ID=OS.ORDER_ID
                INNER JOIN "bdm_customers" as C
                ON OS.CUSTOMER_ID=C.customer_id
                INNER JOIN "bdm_rfm" as RF
                ON RF.CUSTOMER_ID=C.customer_id WHERE RF.SEGMENT IN ({ls})
            )   
            )) as ALLSELL
        GROUP BY ALLSELL.product_manufacturer, ALLSELL.TYPE
        ORDER BY REV DESC;
        '''
    df = session.sql(queryAll).collect()
    df=pd.DataFrame(df)
    return df

query=f'''
    SELECT SEGMENT, COUNT(*) as c
    FROM "bdm_rfm" 
    GROUP BY SEGMENT;'''
df = session.sql(query).collect()
cols=st.columns(5)
cols2=st.columns(5)
df=pd.DataFrame(df)
for index, k in df.iterrows():
    if index<len(cols):
        with cols[index]:
            st.metric(k['SEGMENT'],k['C'])
    else:
        with cols2[5-index]:
            st.metric(k['SEGMENT'],k['C'])

query=f'''
    SELECT DISTINCT SEGMENT FROM "bdm_rfm";
'''
# segment = pd.read_sql(query, session)
segment=df['SEGMENT'].unique()


st.markdown("## Simulate Discount on Segments") 

segTarget=st.multiselect("Segment Target:",segment, default=["Hibernating customers","Loyal"])
if len(segTarget)>0: 
    c,c2=st.columns(2)
    discount=c.slider("Discount on Target Segment:",min_value=0,max_value=50,step=5,value=5)
    increase=c2.slider("Anticipated Sales Increase on Target Segment:",min_value=0,max_value=50,value=20)
    df2=getRevSplit(segTarget,discount,increase)
    dfAll=df2.loc[df2['TYPE'].isin(['ALL','EXCEPT'])] 
    dfAll=dfAll.groupby('PR',as_index=False).sum()
    dfAll.sort_values(by=['PR'],inplace=True)
    dfAll=dfAll[['PR','REV']]
    result = dfAll.to_json(orient="values")
    parsed = json.loads(result)
    dfDisc=df2.loc[df2['TYPE'].isin(['ALL','DISC'])]
    dfDisc=dfDisc.groupby('PR',as_index=False).sum()
    dfDisc.sort_values('PR')
    dfDisc=dfDisc[['PR','REV']]
    resultDisc = dfDisc.to_json(orient="values")
    parsedDisc = json.loads(resultDisc) 
    cat=json.loads(dfDisc.PR.to_json(orient="values"))
    co,co1=st.columns(2)
    cur=dfAll.sum().REV
    sim=dfDisc.sum().REV
    co.metric("Revenue Current","{:,.0f}€".format(cur).replace(',', ' '))
    co1.metric("Revenue Impact","{:,.0f}€".format(sim).replace(',', ' '),str(round(((sim/cur)-1)*100,2)+0.01) + "%")
    chartdef2={
        "chart": {
                "type": 'column',
                "zoomType": 'x',
                'zooming': {
                    'mouseWheel': False
                }
            },
            "xAxis": {
                "type": 'category'
            },
            "yAxis":{
                "title":""
            },
            "title": {
                "text": ''
            },
            "series": [
                    {   "type": 'column',
                        "dataSorting": {
                            "enabled": True,
                            "matchByName": True
                        },
                    "name":"Actual Revenue",
                    "data": parsed
                    },
                    {  "type": 'column',
                        "dataSorting": {
                            "enabled": True,
                            "matchByName": True
                        },
                    "name":"Simulated Revenue",
                    "data": parsedDisc,
                    "color":"red"
                }
            ]
            
    }
    hct.streamlit_highcharts(chartdef2)
    st.markdown("## Trigger Marketing Campaign") 
    seg=",".join("'{0}'".format(w) for w in segTarget)
    query=f'''SELECT RFM.CUSTOMER_ID, RFM.SEGMENT, CUST.CUSTOMER_EMAIL, '{discount}%' as DISCOUNT
        FROM "bdm_rfm" as RFM
        INNER JOIN  "bdm_customers" as CUST
        ON RFM.CUSTOMER_ID=CUST.CUSTOMER_ID
        WHERE RFM.actual_state=true AND RFM.SEGMENT in ({seg});
        '''
    dfCust =pd.DataFrame(session.sql(query).collect())
    st.dataframe(dfCust,use_container_width=True)
    colB,cc=st.columns(2)    
    bck=colB.selectbox("Select Keboola Bucket:",key="bck",options= list(map(lambda v: v['id'], buckets)))
    date_time = datetime.now().strftime("%m_%d_%Y_%H_%M_%S")
    value = kb.keboola_upload(
        keboola_URL=keboola_URL,
        keboola_key=keboola_key,
        keboola_table_name="Marketing_Discount_" +date_time,
        keboola_bucket_id=bck,
        keboola_file_path=saveFile(dfCust),
        keboola_primary_key=[""],
        label="UPLOAD TABLE",
        key="two"
    )
    value
#TODO
