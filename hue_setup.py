#!/usr/bin/env python3

import json
import sys
import os

import requests
import dotenv

dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.realpath(__file__)), '.env'))

HOST = requests.get('https://www.meethue.com/api/nupnp').json()[0]['internalipaddress']
USERNAME = os.environ['USERNAME']
API_URL = 'http://{}/api/{}'.format(HOST, USERNAME)

LAT='37N'
LONG='122W'

LR_LIGHT_IDS = ['1', '2', '3']
EMMA_LIGHT_IDS = ['4', '5', '6']
LIGHT_IDS = LR_LIGHT_IDS + EMMA_LIGHT_IDS

LR_SWITCH_ID = '2'
EMMA_SWITCH_ID = '3'

SCENE_JSONS = [{
    'name': 'off',
    'lights': {
        light_id: {
            'on': False
        }
        for light_id in LIGHT_IDS
    }
}, {
    'name': 'white',
    'lights': {
        light_id: {
            'on': True,
            'bri': 255,
            'sat': 0
        }
        for light_id in LIGHT_IDS
    }
}, {
    'name': 'prewhite1hour',
    'lights': {
        light_id: {
            'on': True,
            'bri': 1,
            'sat': 0
        }
        for light_id in LIGHT_IDS
    }
}, {
    'name': 'white1hour',
    'lights': {
        light_id: {
            'on': True,
            'bri': 255,
            'sat': 0,
            'transitiontime': 10 * 60 * 60 # given in multiples of .1 seconds
        }
        for light_id in LIGHT_IDS
    }
}, {
    'name': 'dim',
    'lights': {
        light_id: {
            'on': True,
            'bri': 100
        }
        for light_id in LIGHT_IDS
    }
}, {
    'name': 'dimred',
    'lights': {
        light_id: {
            'on': True,
            'bri': 100,
            'hue': 0,
            'sat': 255
        }
        for light_id in LIGHT_IDS
    }
}, {
    'name': 'colorloop',
    'lights': {
        light_id: {
            'on': True,
            'bri': 255,
            'sat': 255,
            'effect': 'colorloop'
        }
        for light_id in LIGHT_IDS
    }
}]

def is_error(response):
    json = response.json()
    return(response.status_code != 200 or (isinstance(json, list) and len(json) != 0 and 'error' in json[0].keys()))

def request(method, path, data=None):
    if data is not None:
        data = json.dumps(data)
    response = method(API_URL+path, data=data)

    if is_error(response):
        print(method.__name__, path, data, file=sys.stderr)
        print(response.status_code, response.content.decode(), file=sys.stderr)
        raise RuntimeError('request failed')
    elif method != requests.get:
        print(method.__name__, path, data)
        print(response.status_code, response.content.decode())

    return response

def create_or_update(resource_type, resource_json):
    name = resource_json['name']
    if name is None or len(name) == 0:
        raise RuntimeError('name is required')

    resources_json = request(requests.get, '/{}'.format(resource_type)).json()
    resource_id = None
    for _resource_id, resource in resources_json.items():
        if resource['name'] == name:
            resource_id = _resource_id
            break

    if resource_id is None:
        response = request(requests.post, '/{}'.format(resource_type), resource_json)
        resource_id = response.json()[0]['success']['id']
        if '/' in resource_id:
            _, _, resource_id = resource_id.rpartition('/')
        return resource_id
    else:
        request(requests.put, '/{}/{}'.format(resource_type, resource_id), resource_json)
        return resource_id

def delete_all(resource_type, condition = None):
    resources_json = request(requests.get, '/{}'.format(resource_type)).json()

    for resource_id, resource_json in resources_json.items():
        if condition is None or condition(resource_json):
            request(requests.delete, '/{}/{}'.format(resource_type, resource_id))

BUTTONS = ['34', '16', '17', '18']

def create_switch_rule(name, sensor_id, button_id, group_id, scene_id):
    json = {
        'name': name,
        'conditions': [
            {
                'address': '/sensors/{}/state/buttonevent'.format(sensor_id),
                'operator': 'eq',
                'value': BUTTONS[button_id - 1]
            },
            {
                'address': '/sensors/{}/state/lastupdated'.format(sensor_id),
                'operator': 'dx'
            }
        ],
        'actions': [
            {
                'address': '/groups/{}/action'.format(group_id),
                'method': 'PUT',
                'body': {
                    'scene': scene_id
                }
            }
        ]
    }
    return create_or_update('rules', json)

def create_group(name, light_ids):
    return create_or_update('groups', { 'name': name, 'lights': light_ids })

def create_scene(scene_json):
    lights_json = scene_json['lights']
    scene_json['lights'] = list(lights_json.keys())
    scene_id = scene_json['name']
    request(requests.put, '/scenes/{}'.format(scene_id), scene_json)
    for light_id, light_json in lights_json.items():
        request(requests.put, '/scenes/{}/lights/{}/state'.format(scene_id, light_id), light_json)
    return scene_id

def create_lr_switch_rule(group_id, button_id, scene_id):
    return create_switch_rule(name='LR B{}'.format(button_id), sensor_id=LR_SWITCH_ID, button_id=button_id, group_id=group_id, scene_id=scene_id)

def create_emma_switch_rule(group_id, button_id, scene_id):
    return create_switch_rule(name='Emma B{}'.format(button_id), sensor_id=EMMA_SWITCH_ID, button_id=button_id, group_id=group_id, scene_id=scene_id)

def configure_daylight_sensor(lat, long, sunriseoffset=0, sunsetoffset=0):
    resource_json = {
        'lat': lat,
        'long': long,
        'sunriseoffset': sunriseoffset,
        'sunsetoffset': sunsetoffset
    }
    return request(requests.put, '/sensors/1/config', resource_json)

def create_daylight_rule(name, group_id, pre_scene_id, scene_id, daylight=True):
    json = {
        'name': name,
        'conditions': [
            {
                "address": "/sensors/1/state/daylight",
                "operator": "eq",
                "value": str(daylight).lower()
            }
        ],
        'actions': [
            {
                'address': '/groups/{}/action'.format(group_id),
                'method': 'PUT',
                'body': {
                    'scene': pre_scene_id
                }
            },
            {
                'address': '/groups/{}/action'.format(group_id),
                'method': 'PUT',
                'body': {
                    'scene': scene_id
                }
            }
        ]
    }
    return create_or_update('rules', json)

def main():
    lr_group_id = create_group('Living Room', LR_LIGHT_IDS)
    emma_group_id = create_group('Emma', EMMA_LIGHT_IDS)

    for scene_json in SCENE_JSONS:
        create_scene(scene_json)

    delete_all('rules', lambda rule_json: 'Default' in rule_json['name'])

    create_lr_switch_rule(lr_group_id, 1, 'white')
    create_lr_switch_rule(lr_group_id, 2, 'off')
    create_lr_switch_rule(lr_group_id, 3, 'dim')
    create_lr_switch_rule(lr_group_id, 4, 'colorloop')

    create_emma_switch_rule(emma_group_id, 1, 'white')
    create_emma_switch_rule(emma_group_id, 2, 'off')
    create_emma_switch_rule(emma_group_id, 3, 'dimred')
    create_emma_switch_rule(emma_group_id, 4, 'colorloop')

    configure_daylight_sensor(LAT, LONG)
    create_daylight_rule('Emma Morning', emma_group_id, 'prewhite1hour', 'white1hour')

if __name__ == '__main__':
    main()
