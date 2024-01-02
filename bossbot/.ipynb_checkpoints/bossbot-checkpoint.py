# -*- coding: utf-8 -*-
import logging
import threading
import time
import re
import json
import random
import string
import requests
import qrcode
import paho.mqtt.client as mqtt
from bossbot import protobuf_json
from bossbot.proto_pb2 import TechwolfChatProtocol


class BossBot(threading.Thread):
    uid = None
    user_id = None
    token = None
    friends = {}
    hostname = 'ws.zhipin.com'
    port = 443
    timeout = 60
    keepAlive = 100
    topic = '/chatws'
    client = None
    session = requests.session()
    jobs=[]

    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "sec-fetch-dest": "empty",
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36\(KHTML, like Gecko) Chrome/80.0.3987.122 Safari/537.36",
        "content-type": "application/json; charset=UTF-8",
        "origin": "https://login.zhipin.com",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "referer": "https://login.zhipin.com/?ka=header-login",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8"
    }

    def __init__(self):
        super().__init__()


    def login(self, uid, user_id, token):
        """
        登陆账号 获取近期对话
        :param uid: 
        :param user_id: 
        :param token: 
        :return:
        """
        self.uid = uid
        self.user_id = user_id
        self.token = token
        self.session.headers.update(self.headers)
        requests.utils.add_dict_to_cookiejar(self.session.cookies,
                                                 { "wt2": user_id,
                                                  'token':token
                                                   })
        zp_token=self.session.get('https://www.zhipin.com/wapi/zppassport/get/zpToken').json().get('zpData').get('token')
        self.session.headers.update({'token':token,'Zp_token': zp_token})
        logging.info('已登陆: uid: %s, user_id: %s, token: %s ,zp_token:%s' % (self.uid, self.user_id, self.token,zp_token))
        self.get_chats()

    def _on_connect(self, client, userdata, flags, rc):
        """
        即时通讯 websocket 连接成功
        :param client:
        :param userdata:
        :param flags:
        :param rc:
        :return:
        """
        logging.info("Connected with result code ", str(rc) , 'user_data',userdata )
        # client.subscribe(self.topic)
        self.on_connect(client, userdata, flags, rc)

    def on_connect(self, client, userdata, flags, rc):
        """
        即时通讯 websocket 连接成功
        :param client:
        :param userdata:
        :param flags:
        :param rc:
        :return:
        """
        pass


    def _on_disconnect(self, client, userdata, rc):
        """
        即时通讯 websocket 断开连接
        :param client:
        :param userdata:
        :param rc:
        :return:
        """
        if rc != 0:
            logging.info("Unexpected disconnection.")

    def _on_message(self, client, userdata, msg):
        """
        收到消息
        :param client:
        :param userdata:
        :param msg: 收到的消息内容
        :return:
        """
        logging.info('_on_message',userdata,msg)
        protocol = TechwolfChatProtocol()
        protocol.ParseFromString(msg.payload)
        data = protobuf_json.pb2json(protocol)
        logging.info('receive: ', json.dumps(data, ensure_ascii=False))
        if data['type'] == 1:
            message = data['messages'][-1]
            body = message['body']


            if message['from']['uid'] not in self.friends and message['from']['uid']!=self.uid:
                self.geek_info(message['from']['uid'])

            if message['to']['uid'] not in self.friends and message['from']['uid']!=self.uid:
                self.geek_info(message['from']['uid'])

            if body['type'] == 1:
                # 文字消息
                self.on_text_message(data, message['from']['uid'], body['text'])
            # elif body['type'] == 7 and message['from']['uid'] != int(self.uid):
            #     # 求简历
            #     pass
            elif body['type'] == 7 and message['to']['uid'] == int(self.uid):
                # 对方请求发简历过来
                self.exchange_accept(message['mid'],message['from']['uid'])
                time.sleep(0.2)
                info = self.friends.get(message['from']['uid'],{}).get("info",{})
                if not info:
                    info = self.geek_info(message['from']['uid'])
                self.download_resume(info)

        elif data['type'] == 4:
            # /message/suggest
            pass
        elif data['type'] == 6:
            # 同步已读未读
            pass

    def download_resume(self,info):
        """
        简历下载函数
        :param msg: 文本内容
        :return:
        """
        pass

    def on_text_message(self, data, boss_id, msg):
        """
        文本 消息回调函数。
        :param data: 收到的完整消息内容
        :param boss_id: 发送次消息的boss的id
        :param msg: 文本内容
        :return:
        """
        logging.info('收到文字消息:', msg)



    def send_message(self, boss_id: str, msg: str):
        """
        发送文本消息
        :param boss_id: 对方boss_id
        :param msg: 消息内容
        :return:
        """
        mid = int(time.time() * 1000)

        chat = {
            "type": 1,
            "messages": [
                {
                    "from": {
                        "uid": self.uid
                    },
                    "to": {
                        "uid": boss_id,
                        "name": self.friends[boss_id].get('info')['encryptUid']
                    },
                    "type": 1,
                    "mid": mid,
                    "time": int(time.time() * 1000),
                    "body": {
                        "type": 1,
                        "templateId": 1,
                        "text": msg
                    },
                    "cmid": mid
                }
            ]
        }
        chat_protocol = protobuf_json.json2pb(TechwolfChatProtocol(), chat)
        logging.info(self.client.publish(self.topic, payload=chat_protocol.SerializeToString(), qos=0) )

    def run(self):
        client_id = 'ws-'+''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(16))#"ws-0EB5DA48EE56AC0A"
        self.client = mqtt.Client(client_id=client_id, clean_session=True,
                                  transport="websockets")
        self.client.username_pw_set(self.token, self.user_id)
        headers = {
            "Cookie": "t=%s; wt2=%s;" % (self.user_id, self.user_id)
        }
        self.client.ws_set_options(path=self.topic, headers=headers)
        self.client.tls_set()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        # self.client.enable_logger(self.logger)

        ##30秒ping一次。60秒的话会断开连接
        self.client.connect(self.hostname, self.port, 30)
        self.client.loop_forever()


    def get_his_msg(self,uid):
        '''
        获取详细的聊天记录
        '''
        his_msg = 'https://www.zhipin.com/wapi/zpchat/boss/historyMsg'
        his_msg_para = {
            'src': 0,
            'gid': uid,
            'maxMsgId': 0,
            'c': 20,
            'page': 1
        }
        r = self.session.get(his_msg, params=his_msg_para)
        return r

    def get_jobs(self):
        r = self.session.get('https://www.zhipin.com/wapi/zpjob/job/data/list')
        self.jobs = [[i['encryptId'], i['jobName']] for i in r.json()['zpData']['data'] ]
        return self.jobs

    def get_friends_list(self,uids):
        '''
        批量获取好友基本信息
        '''
        d = {'friendIds': uids,'dzFriendIds':None }
        r= self.session.post('https://www.zhipin.com/wapi/zprelation/friend/getBossFriendListV2.json',data=d,headers={'Content-Type':'application/x-www-form-urlencoded'})
        for friend in r.json()['zpData']['friendList']:
            self.friends[friend['uid']].update(friend)
        
    def get_chats(self):
        '''
        获取最近的对话
        '''
        filterByLabel_data={'labelId': '0',
        'encJobId':None }
        r=self.session.post('https://www.zhipin.com/wapi/zprelation/friend/filterByLabel',data=filterByLabel_data,headers={'content-type': 'application/x-www-form-urlencoded'})
        self.friends = { i['friendId']:i for i in r.json()['zpData']['result'] if i['friendId']>10000000 and i['updateTime']>(time.time()*1000 - 3600*24*5*1000)  }
        uids = list(self.friends.keys())
        for i in range(0, len(uids), 82):
            sublist = uids[i:i+82]  # 从索引i开始到i+50（不包含i+50）
            self.get_friends_list(sublist)
            time.sleep(0.04)
        return self.friends

    def exchange_request(self,uid):
        '''
        请求简历
        '''
        time.sleep(0.2)
        info = self.friends.get(uid,{}).get('info')
        if not info:
            return
        request_url = 'https://www.zhipin.com/wapi/zpchat/exchange/request'
        request_para = {
            'type': 4,
            'securityId': self.friends[uid].get('info')['securityId']
        }
        logging.info('exchange_request ', self.session.post(request_url, data=request_para))


    def exchange_accept(self, mid, uid):
        '''
        接收简历 
        '''
        info = self.geek_info(uid)
        if not info:
            return
            # self.geek_info(uid)
            # self.friends[uid].get('info')

        accept_url = 'https://www.zhipin.com/wapi/zpchat/exchange/accept'
        accept_para = {
            'mid': mid,
            'type': 3,
            'securityId': info['securityId']
        }
        r=self.session.post(accept_url, data=accept_para)
        logging.info('exchange_accept ',r,r.text)

    
    def geek_info(self, uid):
        '''
        获取牛人详细信息，更新self.friends
        '''
        if uid <10000000:
            return {}
        info_url = 'https://www.zhipin.com/wapi/zpjob/chat/geek/info'
        info_para = {
            'uid': uid,
            'geekSource': '0',
        }
        r = self.session.get(info_url, params=info_para)
        if uid not in self.friends:
            self.friends[uid]={}
        if 'data' not in r.json()['zpData']:
            logging.warning('err geek_info',uid,r.json())
            del self.friends[uid]
        else:
            self.friends[uid]['info']=r.json()['zpData']['data']

            return r.json()['zpData']['data']

    def change_note(self,info,note):
        '''
        更改候选人的备注
        '''
        url='https://www.zhipin.com/wapi/zprelation/noteandlabel/save.json'  
        para={
            'encryptFriendId': info['encryptUid'],
            'securityId': info['securityId'],
            'labels': '',
            'note': note
        }
        r = self.session.post(url,data=para)
        self.session.headers['content-type']='application/x-www-form-urlencoded'
        logging.info('change_note',info,note,r.text)
        
