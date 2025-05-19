import requests
from bs4 import BeautifulSoup
# Данные для проверки: login = "ItsMeReally"; password = "N68-8Yy-A9N-EFd!"


def auth(username, password):
    data = {
        "username": username,
        "password": password
    }
    url_auth = 'https://elfin-circular-octagon.glitch.me/login'
    url_subscribe = 'https://elfin-circular-octagon.glitch.me/subscription'
    session = requests.Session()
    session.post(url_auth, data=data)
    response = session.get(url_subscribe).text
    soup = BeautifulSoup(response, 'lxml')
    block_main = soup.find('div', class_='container content')
    block_data_1 = block_main.find('div', class_='alert alert-info mb-4')
    block_data_2 = block_data_1.find_all('p')
    block_costs_1 = block_main.find('div', class_='row justify-content-center')
    block_costs_2 = block_costs_1.find('div', class_='card-body text-center')
    block_costs_3 = block_costs_2.find('h4', class_='text-primary')
    return [int(str(block_data_2[0]).split()[-1].split(".")[0]), int(str(block_costs_3)[25: -11])]


if __name__ == '__main__':
    print(auth("Ar", "P2&iiPlpRyt2"))
#[3:-4] [25:-5]