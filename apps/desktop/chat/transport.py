import json

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWebSockets import QWebSocket


class BackendClient(QObject):
    event = Signal(dict)
    failure = Signal(str)
    ready = Signal()

    def __init__(self, token: str, parent=None):
        super().__init__(parent)
        self.token = token
        self.network = QNetworkAccessManager(self)
        self.socket = QWebSocket(parent=self)
        self.socket.connected.connect(self.authenticate)
        self.socket.textMessageReceived.connect(self.receive)
        self.socket.disconnected.connect(
            lambda: self.failure.emit("Conexão encerrada. Use Reconectar.")
        )
        self.socket.errorOccurred.connect(lambda _: self.failure.emit(self.socket.errorString()))
        self.authenticated = False
        self.socket.disconnected.connect(self.reset)

    def reset(self):
        self.authenticated = False

    def connect_backend(self):
        self.socket.open(QUrl("ws://127.0.0.1:8765/v1/chat"))

    def authenticate(self):
        self.send({"v": 1, "type": "auth", "token": self.token})

    def send(self, payload: dict):
        self.socket.sendTextMessage(json.dumps(payload))

    def receive(self, raw: str):
        try:
            event = json.loads(raw)
            if event.get("type") == "ready":
                self.authenticated = True
                self.ready.emit()
            self.event.emit(event)
        except (ValueError, AttributeError):
            self.failure.emit("Resposta inválida do backend")

    def rest(self, method: str, path: str, payload, callback):
        request = QNetworkRequest(QUrl("http://127.0.0.1:8765" + path))
        request.setRawHeader(b"Authorization", ("Bearer " + self.token).encode())
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setTransferTimeout(45000)
        body = json.dumps(payload).encode() if payload is not None else b""
        reply = self.network.sendCustomRequest(request, method.encode(), body)

        def finished():
            try:
                data = json.loads(bytes(reply.readAll()))
                status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                if status is None or status >= 400:
                    self.failure.emit(str(data.get("detail", "Backend indisponível")))
                else:
                    callback(data)
            except (ValueError, TypeError):
                self.failure.emit("Falha na comunicação com o backend")
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
