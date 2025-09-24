# Начало запроса
`opcode 6` 
## Payload
``` json
{
  "userAgent": {
    "deviceType": "WEB"
  }
}
```
## Return
``` json
null
```
# Авторизация
## Вход
`opcode 17`
### Payload
``` json
{
	"payload": {
		"phone": "[PHONE_NUMBER]",
		"type": "START_AUTH",
		"language": "ru"
	}
}
```
### Return
``` json
{
	"requestMaxDuration": 60000,
	"requestCountLeft": 10,
	"altActionDuration": 60000,
	"codeLength": 6,
	"token": "[TOKEN]"
}
```

---

`opcode 18`
## Payload
``` json
{
	"token": "[TOKEN]",
	"verifyCode": "[CODE]",
	"authTokenType": "CHECK_CODE"
}
```
## Return
``` json
{
		"tokenAttrs": {
			"LOGIN": {
				"token": "[TOKEN]"
			}
		},
		"profile": "[PROFILE_JSON]"
}
```
## Регистрация
### TODO

# Инициализация

## Синхронизация
`opcode 19` 
### Payload
``` json
{
	"interactive": true,
	"token": "[TOKEN]",
	"chatsCount": 40,
	"chatsSync": 0,
	"contactsSync": 0,
	"presenceSync": 0,
	"draftsSync": 0
}
```
### Return
``` json
{
  "ver": 11,
  "cmd": 1,
  "seq": 1,
  "opcode": 19,
  "payload": {
    "videoChatHistory": false,
    "calls": [],
    "profile": "[PROFILE]",
    "chats": "[CHATS]",
    "chatMarker": 0,
    "messages": {},
    "drafts": {
      "chats": {
        "saved": {},
        "discarded": {}
      },
      "users": {
        "saved": {},
        "discarded": {}
      }
    },
    "time": 1757275663175,
    "presence": {
      "13446207": {
        "seen": 1757275663,
        "on": "ON"
      }
    },
    "config": "[CONFIG]",
    "contacts": []
  }
}
```

## Обновление токена

`opcode 158`
## Payload
``` json
{}
```
## Return
``` json
{
	"token_lifetime_ts":"[SOME_TIME_IDK]",
	"token_refresh_ts":"[SOME_TIME_IDK_2]", // что это значит?
	"token":"[NEW_TOKEN]"
}
```

# Чаты

## Получение собщений
`opcode 49`
## Payload
``` json
{
	"chatId": "[CHAT_ID]",
	"from": "[TIME_START_POINT]",
	"forward": "[GET_N_MSGS_FROM_POINT]",
	"backward": "[GET_N_MSGS_FROM_POINT]",
	"getMessages": true // что это?
}
```
## Return
``` json
{
	"messages": "[MSGS]"
}
```
---

