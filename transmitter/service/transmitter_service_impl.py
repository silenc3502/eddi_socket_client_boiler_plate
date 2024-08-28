import json
import socket
import threading
from time import sleep

from critical_section.manager import CriticalSectionManager
from response_generator.generator import ResponseGenerator
from response_generator.packet_length_response import PacketLengthResponse
from transmitter.repository.transmitter_repository_impl import TransmitterRepositoryImpl
from transmitter.service.transmitter_service import TransmitterService
from utility.color_print import ColorPrinter


class TransmitterServiceImpl(TransmitterService):
    __instance = None

    __responseClassMapInstance = None
    __responseGeneratorInstance = ResponseGenerator.getInstance()

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
            cls.__instance.__transmitterRepository = TransmitterRepositoryImpl.getInstance()

            cls.__instance.__criticalSectionManager = CriticalSectionManager.getInstance()

            cls.__instance.__transmitterLock = threading.Lock()

        return cls.__instance

    @classmethod
    def getInstance(cls):
        if cls.__instance is None:
            cls.__instance = cls()

        return cls.__instance

    def requestToInjectUserDefinedResponseClassMapInstance(self, responseClassMapInstance):
        self.__responseClassMapInstance = responseClassMapInstance
        self.__responseGeneratorInstance.requestToInjectUserDefinedResponseClassMapInstance(responseClassMapInstance)

    def requestToInjectClientSocket(self, clientSocket):
        self.__transmitterRepository.injectClientSocket(clientSocket)

    def requestToInjectExecutorTransmitterChannel(self, ipcExecutorTransmitterChannel):
        self.__transmitterRepository.injectExecutorTransmitterChannel(ipcExecutorTransmitterChannel)

    # def __blockToAcquireSocket(self):
    #     if self.__transmitterRepository.getClientSocket() is None:
    #         return True
    #
    #     return False

    def __blockToAcquireSocket(self):
        if self.__criticalSectionManager.getClientSocket() is None:
            return True

        return False

    def requestToTransmitResult(self):
        while self.__blockToAcquireSocket():
            ColorPrinter.print_important_message("Transmitter: Try to get SSL Socket")
            sleep(0.5)

        ColorPrinter.print_important_message("Transmitter 구동 성공!")

        clientSocketObject = self.__criticalSectionManager.getClientSocket()
        ColorPrinter.print_important_data("requestToTransmitResult() -> clientSocketObject", clientSocketObject)

        while True:
            try:
                willBeTransmitResponse = self.__transmitterRepository.acquireWillBeTransmit()
                ColorPrinter.print_important_data("Transmitter -> 전송할 데이터", willBeTransmitResponse)

                protocolNumber, response = willBeTransmitResponse
                socketResponse = self.__responseGeneratorInstance.generate(protocolNumber, response)
                # socketResponse = ResponseGenerator.generate(protocolNumber, response)

                if socketResponse is None:
                    continue

                if clientSocketObject.fileno() == -1:  # 소켓이 유효한지 확인
                    raise socket.error("Socket is closed or invalid")

                dictionarizedResponse = socketResponse.toDictionary()
                serializedRequestData = json.dumps(dictionarizedResponse, ensure_ascii=False)
                
                # TODO: 전체 패킷 길이를 계산해야함
                # 계산하여 수신측이 지속적으로 정보를 수신할 수 있도록 만들어야함
                packetLength = len(serializedRequestData)
                ColorPrinter.print_important_data("전체 패킷 길이", packetLength)

                # 일관성 유지를 위해 PacketLengthResponse를 구성하도록 만든다.
                packetLengthResponse = PacketLengthResponse(packetLength)
                dictionarizedPacketLengthResponse = packetLengthResponse.toDictionary()
                serializedPacketLengthData = json.dumps(dictionarizedPacketLengthResponse, ensure_ascii=False)

                with self.__transmitterLock:
                    # 전체 패킷 길이 전송
                    self.__transmitterRepository.transmit(clientSocketObject, serializedPacketLengthData)
                    # 실제 내용물 전송
                    self.__transmitterRepository.transmit(clientSocketObject, serializedRequestData)

            except (socket.error, BrokenPipeError) as exception:
                return None

            except socket.error as exception:
                print("전송 중 에러")

            except Exception as exception:
                print(f"Transmitter: {str(exception)}")

            finally:
                sleep(0.5)



