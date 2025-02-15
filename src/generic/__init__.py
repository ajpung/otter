import abc
import datetime


class Simulated(abc.ABC):
    @abc.abstractmethod
    def simulate_to(self, dt: datetime.datetime):
        pass
