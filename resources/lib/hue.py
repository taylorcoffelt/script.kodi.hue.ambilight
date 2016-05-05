import xbmc
import socket
import json
import time
import logging

from tools import *

try:
  import requests
except ImportError:
  notify("Kodi Hue", "ERROR: Could not import Python requests")

class Hue:
  params = None
  connected = None
  last_state = None
  light = None
  ambilight_dim_light = None
  pauseafterrefreshchange = 0

  def __init__(self, settings, args):
    #Logs are good, mkay.
    self.logger = Logger()
    if settings.debug:
      self.logger.debug()

    #get settings
    self.settings = settings
    self._parse_argv(args)

    #if there's a bridge user, lets instantiate the lights (only if we're connected).
    if self.settings.bridge_user not in ["-", "", None] and self.connected:
      self.update_settings()

    if self.params == {}:
      self.logger.debuglog("params: %s" % self.params)
      #if there's a bridge IP, try to talk to it.
      if self.settings.bridge_ip not in ["-", "", None]:
        result = self.test_connection()
        if result:
          self.update_settings()
    elif self.params['action'] == "discover":
      self.logger.debuglog("Starting discovery")
      notify("Bridge Discovery", "starting")
      hue_ip = self.start_autodiscover()
      if hue_ip != None:
        notify("Bridge Discovery", "Found bridge at: %s" % hue_ip)
        username = self.register_user(hue_ip)
        self.logger.debuglog("Updating settings")
        self.settings.update(bridge_ip = hue_ip)
        self.settings.update(bridge_user = username)
        notify("Bridge Discovery", "Finished")
        self.test_connection()
        self.update_settings()
      else:
        notify("Bridge Discovery", "Failed. Could not find bridge.")
    elif self.params['action'] == "reset_settings":
      self.logger.debuglog("Reset Settings to default.")
      self.logger.debuglog(__addondir__)
      os.unlink(os.path.join(__addondir__,"settings.xml"))
      #self.settings.readxml()
      #xbmcgui.Window(10000).clearProperty("script.kodi.hue.ambilight" + '_running')
      #__addon__.openSettings()
    else:
      # not yet implemented
      self.logger.debuglog("unimplemented action call: %s" % self.params['action'])

    #detect pause for refresh change (must reboot for this to take effect.)
    response = json.loads(xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Settings.GetSettingValue", "params":{"setting":"videoplayer.pauseafterrefreshchange"},"id":1}'))
    #logger.debuglog(isinstance(response, dict))
    if "result" in response and "value" in response["result"]:
      pauseafterrefreshchange = int(response["result"]["value"])

    if self.connected:
      if self.settings.misc_initialflash:
        self.flash_lights()

  def start_autodiscover(self):
    port = 1900
    ip = "239.255.255.250"

    address = (ip, port)
    data = """M-SEARCH * HTTP/1.1
    HOST: %s:%s
    MAN: ssdp:discover
    MX: 3
    ST: upnp:rootdevice
    """ % (ip, port)
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) #force udp
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    client_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    hue_ip = None
    num_retransmits = 0
    while(num_retransmits < 10) and hue_ip == None:
      num_retransmits += 1
      try:
        client_socket.sendto(data, address)
        recv_data, addr = client_socket.recvfrom(2048)
        self.logger.debuglog("received data during autodiscovery: "+recv_data)
        if "IpBridge" in recv_data and "description.xml" in recv_data:
          hue_ip = recv_data.split("LOCATION: http://")[1].split(":")[0]
        time.sleep(1)
      except socket.timeout:
        break #if the socket times out once, its probably not going to complete at all. fallback to nupnp.

    if hue_ip == None:
      #still nothing found, try alternate api
      r=requests.get("https://www.meethue.com/api/nupnp", verify=False) #verify false hack until meethue fixes their ssl cert.
      j=r.json()
      if len(j) > 0:
        hue_ip=j[0]["internalipaddress"]
        self.logger.debuglog("meethue nupnp api returned: "+hue_ip)
      else:
        self.logger.debuglog("meethue nupnp api did not find bridge")
        
    return hue_ip

  def register_user(self, hue_ip):
    device = "kodi-hue-addon"
    data = '{"devicetype": "%s#%s"}' % (device, xbmc.getInfoLabel('System.FriendlyName')[0:19])
    self.logger.debuglog("sending data: %s" % data)

    r = requests.post('http://%s/api' % hue_ip, data=data)
    response = r.text
    while "link button not pressed" in response:
      self.logger.debuglog("register user response: %s" % r)
      notify("Bridge Discovery", "Press link button on bridge")
      r = requests.post('http://%s/api' % hue_ip, data=data)
      response = r.text 
      time.sleep(3)

    j = r.json()
    self.logger.debuglog("got a username response: %s" % j)
    username = j[0]["success"]["username"]

    return username

  def flash_lights(self):
    self.logger.debuglog("class Hue: flashing lights")
    if self.settings.light == 0:
      self.light.flash_light()
    else:
      self.light[0].flash_light()
      if self.settings.light > 1:
        xbmc.sleep(1)
        self.light[1].flash_light()
      if self.settings.light > 2:
        xbmc.sleep(1)
        self.light[2].flash_light()
    
  def _parse_argv(self, args):
    try:
        self.params = dict(arg.split("=") for arg in args.split("&"))
    except:
        self.params = {}

  def test_connection(self):
    self.logger.debuglog("testing connection")
    r = requests.get('http://%s/api/%s/config' % \
      (self.settings.bridge_ip, self.settings.bridge_user))
    test_connection = r.text.find("name")
    if not test_connection:
      notify("Failed", "Could not connect to bridge")
      self.connected = False
    else:
      notify("Kodi Hue", "Connected")
      self.connected = True
    return self.connected

  # #unifed light action method. will replace dim_lights, brighter_lights, partial_lights
  # def light_actions(self, action, lights=None):
  #   if lights == None:
  #     #default for method
  #     lights = self.light

  #   self.last_state = action

  #   if isinstance(lights, list):
  #     #array of lights
  #     for l in lights:
  #       if action == "dim":
  #         l.dim_light()
  #       elif action == "undim":
  #         l.brighter_light()
  #       elif action == "partial":
  #         l.partial_light()
  #   else:
  #     #group
  #     if action == "dim":
  #       lights.dim_light()
  #     elif action == "undim":
  #       lights.brighter_light()
  #     elif action == "partial":
  #       lights.partial_light()

  def dim_lights(self):
    self.logger.debuglog("class Hue: dim lights")
    self.last_state = "dimmed"
    if self.settings.light == 0:
      self.light.dim_light()
    else:
      self.light[0].dim_light()
      if self.settings.light > 1:
        xbmc.sleep(1)
        self.light[1].dim_light()
      if self.settings.light > 2:
        xbmc.sleep(1)
        self.light[2].dim_light()
        
  def brighter_lights(self):
    self.logger.debuglog("class Hue: brighter lights")
    self.last_state = "brighter"
    if self.settings.light == 0:
      self.light.brighter_light()
    else:
      self.light[0].brighter_light()
      if self.settings.light > 1:
        xbmc.sleep(1)
        self.light[1].brighter_light()
      if self.settings.light > 2:
        xbmc.sleep(1)
        self.light[2].brighter_light()

  def partial_lights(self):
    self.logger.debuglog("class Hue: partial lights")
    self.last_state = "partial"
    if self.settings.light == 0:
      self.light.partial_light()
    else:
      self.light[0].partial_light()
      if self.settings.light > 1:
        xbmc.sleep(1)
        self.light[1].partial_light()
      if self.settings.light > 2:
        xbmc.sleep(1)
        self.light[2].partial_light()

  def update_settings(self):
    self.logger.debuglog("class Hue: update settings")
    self.logger.debuglog(self.settings)
    if self.settings.light == 0:
      self.logger.debuglog("creating Group instance")
      self.light = Group(self.settings)
    elif self.settings.light > 0:
      self.logger.debuglog("creating Light instances")
      self.light = [None] * self.settings.light
      self.light[0] = Light(self.settings.light1_id, self.settings)
      if self.settings.light > 1:
        xbmc.sleep(1)
        self.light[1] = Light(self.settings.light2_id, self.settings)
      if self.settings.light > 2:
        xbmc.sleep(1)
        self.light[2] = Light(self.settings.light3_id, self.settings)
    #ambilight dim
    if self.settings.ambilight_dim:
      if self.settings.ambilight_dim_light == 0:
        self.logger.debuglog("creating Group instance for ambilight dim")
        self.ambilight_dim_light = Group(self.settings, self.settings.ambilight_dim_group_id)
      elif self.settings.ambilight_dim_light > 0:
        self.logger.debuglog("creating Light instances for ambilight dim")
        self.ambilight_dim_light = [None] * self.settings.ambilight_dim_light
        self.ambilight_dim_light[0] = Light(self.settings.ambilight_dim_light1_id, self.settings)
        if self.settings.ambilight_dim_light > 1:
          xbmc.sleep(1)
          self.ambilight_dim_light[1] = Light(self.settings.ambilight_dim_light2_id, self.settings)
        if self.settings.ambilight_dim_light > 2:
          xbmc.sleep(1)
          self.ambilight_dim_light[2] = Light(self.settings.ambilight_dim_light3_id, self.settings)

class Light:
  start_setting = None
  group = False
  livingwhite = False
  fullSpectrum = False

  def __init__(self, light_id, settings):
    self.logger = Logger()
    if settings.debug:
      self.logger.debug()

    self.bridge_ip    = settings.bridge_ip
    self.bridge_user  = settings.bridge_user
    self.mode         = settings.mode
    self.light        = light_id
    self.dim_time     = settings.dim_time
    self.proportional_dim_time = settings.proportional_dim_time
    self.override_hue = settings.override_hue
    self.dimmed_bri   = settings.dimmed_bri
    self.dimmed_hue   = settings.dimmed_hue
    self.override_sat = settings.override_sat
    self.dimmed_sat   = settings.dimmed_sat
    self.undim_sat   = settings.undim_sat
    self.override_paused = settings.override_paused
    self.paused_bri   = settings.paused_bri
    self.undim_bri    = settings.undim_bri
    self.undim_hue    = settings.undim_hue
    self.override_undim_bri = settings.override_undim_bri
    self.force_light_on = settings.force_light_on
    self.force_light_group_start_override = settings.force_light_group_start_override

    self.onLast = True
    self.hueLast = 0
    self.satLast = 0
    self.valLast = 0

    self.get_current_setting()
    self.s = requests.Session()

  def request_url_put(self, url, data):
    #if self.start_setting['on']: #Why? 
    try:
      response = self.s.put(url, data=data)
      self.logger.debuglog("response: %s" % response)
    except:
      self.logger.debuglog("exception in request_url_put")
      pass # probably a timeout

  def get_current_setting(self):
    self.logger.debuglog("get_current_setting. requesting from: http://%s/api/%s/lights/%s" % \
      (self.bridge_ip, self.bridge_user, self.light))
    r = requests.get("http://%s/api/%s/lights/%s" % \
      (self.bridge_ip, self.bridge_user, self.light))
    j = r.json()

    if isinstance(j, list) and "error" in j[0]:
      # something went wrong.
      err = j[0]["error"]
      if err["type"] == 3:
        notify("Light Not Found", "Could not find light %s in bridge." % self.light)
      else:
        notify("Bridge Error", "Error %s while talking to the bridge" % err["type"])
      raise ValueError("Bridge Error", err["type"], err)
      return

    #no error, keep going
    self.start_setting = {}
    state = j['state']
    #self.logger.debuglog("current_setting: %r" % state)
    self.start_setting['on'] = state['on']
    self.start_setting['bri'] = state['bri']
    self.onLast = state['on']
    self.valLast = state['bri']
    
    modelid = j['modelid']
    self.fullSpectrum = ((modelid == 'LST001') or (modelid == 'LLC007'))

    if state.has_key('hue'):
      self.start_setting['hue'] = state['hue']
      self.start_setting['sat'] = state['sat']
      self.hueLast = state['hue']
      self.satLast = state['sat']
    else:
      self.livingwhite = True

    self.logger.debuglog("light %s start settings: %s" % (self.light, self.start_setting))

  # def set_light(self, data):
  #   self.logger.debuglog("set_light: %s: %s" % (self.light, data))
  #   self.request_url_put("http://%s/api/%s/lights/%s/state" % \
  #     (self.bridge_ip, self.bridge_user, self.light), data=data)

  def set_light2(self, hue, sat, bri, duration=None):

    if self.start_setting["on"] == False and self.force_light_on == False:
      # light was not on, and settings say we should not turn it on
      self.logger.debuglog("light %s was off, settings say we should not turn it on" % self.light)
      return

    data = {}

    if not self.livingwhite:
      if not hue is None:
        if not hue == self.hueLast:
          data["hue"] = hue
          self.hueLast = hue
      if not sat is None:
        if not sat == self.satLast:
          data["sat"] = sat
          self.satLast = sat

    self.logger.debuglog("light %s: onLast: %s, valLast: %s" % (self.light, self.onLast, self.valLast))
    if bri > 0:
      if self.onLast == False: #don't send on unless we have to (performance)
        data["on"] = True
        self.onLast = True
      data["bri"] = bri
    else:
      data["on"] = False
      self.onLast = False

    time = 0
    if duration is None:
      if self.proportional_dim_time and self.mode != 0: #only if its not ambilight mode too
        self.logger.debuglog("last %r, next %r, start %r, finish %r" % (self.valLast, bri, self.start_setting['bri'], self.dimmed_bri))
        difference = abs(float(bri) - self.valLast)
        total = float(self.start_setting['bri']) - self.dimmed_bri
        if total != 0:
          proportion = difference / total
          time = int(round(proportion * self.dim_time))
      else:
        time = self.dim_time
    else:
      time = duration

    self.valLast = bri # moved after time calclation to know the previous value (important)

    data["transitiontime"] = time
    
    dataString = json.dumps(data)

    self.logger.debuglog("set_light2: %s: %s" % (self.light, dataString))
    
    self.request_url_put("http://%s/api/%s/lights/%s/state" % \
      (self.bridge_ip, self.bridge_user, self.light), data=dataString)

  def flash_light(self):
    self.dim_light()
    time.sleep(self.dim_time/10)
    self.brighter_light()

  def dim_light(self):
    if self.override_hue:
      hue = self.dimmed_hue
    else:
      hue = None

    if self.override_sat:
      sat = self.dimmed_sat
    else:
      sat = None

    self.set_light2(hue, sat, self.dimmed_bri)

  def brighter_light(self):
    if self.override_undim_bri:
      bri = self.undim_bri
    else:
      bri = self.start_setting['bri']

    if not self.livingwhite:
      if self.override_sat:
        sat = self.undim_sat
      else:
        sat = self.start_setting['sat']
      if self.override_hue:
        hue = self.undim_hue
      else:
        hue = self.start_setting['hue']
    else:
      sat = None
      hue = None

    self.set_light2(hue, sat, bri)

  def partial_light(self):
    if self.override_paused:
      bri = self.paused_bri

      if not self.livingwhite:
        if self.override_sat:
          sat = self.undim_sat
        else:
          sat = self.start_setting['sat']

        if self.override_hue:
          hue = self.undim_hue
        else:
          hue = self.start_setting['hue']
      else:
        sat = None
        hue = None

      self.set_light2(hue, sat, bri)
    else:
      #not enabled for dimming on pause
      self.brighter_light()

class Group(Light):
  group = True
  lights = {}

  def __init__(self, settings, group_id=None):
    if group_id==None:
      self.group_id = settings.group_id
    else:
      self.group_id = group_id

    self.logger = Logger()
    if settings.debug:
      self.logger.debug()

    Light.__init__(self, settings.light1_id, settings)
    
    for light in self.get_lights():
      tmp = Light(light, settings)
      tmp.get_current_setting()
      #if tmp.start_setting['on']: #TODO: Why only add these if they're on?
      self.lights[light] = tmp

  def __len__(self):
    return 0

  def get_lights(self):
    try:
      r = requests.get("http://%s/api/%s/groups/%s" % \
        (self.bridge_ip, self.bridge_user, self.group_id))
      j = r.json()
    except:
      self.logger.debuglog("WARNING: Request fo bridge failed")
      #notify("Communication Failed", "Error while talking to the bridge")

    try:
      return j['lights']
    except:
      # user probably selected a non-existing group
      self.logger.debuglog("Exception: no lights in this group")
      return []

  # def set_light(self, data):
  #   self.logger.debuglog("set_light: %s" % data)
  #   Light.request_url_put(self, "http://%s/api/%s/groups/%s/action" % \
  #     (self.bridge_ip, self.bridge_user, self.group_id), data=data)

  def set_light2(self, hue, sat, bri, duration=None):

    if self.start_setting["on"] == False and self.force_light_on == False:
      # light was not on, and settings say we should not turn it on
      self.logger.debuglog("group %s was off, settings say we should not turn it on" % self.group_id)
      return

    data = {}

    if not self.livingwhite:
      if not hue is None:
        if not hue == self.hueLast:
          data["hue"] = hue
          self.hueLast = hue
      if not sat is None:
        if not sat == self.satLast:
          data["sat"] = sat
          self.satLast = sat

    if bri > 0:
      if self.onLast == False: #don't sent on unless we have to. (performance)
        data["on"] = True
        self.onLast = True
      data["bri"] = bri
    else:
      data["on"] = False
      self.onLast = False

    if duration is None:
      if self.proportional_dim_time and self.mode != 0: #only if its not ambilight mode too
        self.logger.debuglog("last %r, next %r, start %r, finish %r" % (self.valLast, bri, self.start_setting['bri'], self.dimmed_bri))
        difference = abs(float(bri) - self.valLast)
        total = float(self.start_setting['bri']) - self.dimmed_bri
        proportion = difference / total
        time = int(round(proportion * self.dim_time))
      else:
        time = self.dim_time
    else:
      time = duration

    self.valLast = bri # moved after time calculation

    data["transitiontime"] = time
    
    dataString = json.dumps(data)

    self.logger.debuglog("set_light2: group_id %s: %s" % (self.group_id, dataString))
    
    self.request_url_put("http://%s/api/%s/groups/%s/action" % \
      (self.bridge_ip, self.bridge_user, self.group_id), data=dataString)

  # def dim_light(self):
  #   for light in self.lights:
  #       self.lights[light].dim_light()

  # def brighter_light(self):
  #     for light in self.lights:
  #       self.lights[light].brighter_light()

  # def partial_light(self):
  #     for light in self.lights:
  #       self.lights[light].partial_light()

  def get_current_setting(self):
    r = requests.get("http://%s/api/%s/groups/%s" % \
      (self.bridge_ip, self.bridge_user, self.group_id))
    j = r.json()
    self.logger.debuglog("response: %s" % j)
    if isinstance(j, list) and "error" in j[0]:
      # something went wrong.
      err = j[0]["error"]
      if err["type"] == 3:
        notify("Group Not Found", "Could not find group %s in bridge." % self.group_id)
      else:
        notify("Bridge Error", "Error %s while talking to the bridge" % err["type"])
      raise ValueError("Bridge Error", err["type"], err)
      return

    #no error, lets keep going
    self.start_setting = {}
    state = j['action']
    #self.logger.debuglog("current_setting: %r" % state)
    
    self.start_setting['on'] = state['on']
    if self.force_light_group_start_override: #override default just in case there is one light on
      for l in self.lights:
        #self.logger.debuglog("light: %s" % self.lights[l])
        if self.lights[l].start_setting['on']:
          self.logger.debuglog("light %s was on, so the group will start as on" % l)
          self.start_setting['on'] = True
          break

    self.start_setting['bri'] = state["bri"]
    if self.force_light_group_start_override:
      for l in self.lights:
        if self.start_setting['bri'] < self.lights[l].start_setting['bri']:
          self.start_setting['bri'] = self.lights[l].start_setting['bri'] #take the brightest of the group.

    self.onLast = self.start_setting['on']
    self.valLast = self.start_setting['bri']
    
    # modelid = j['modelid']
    # self.fullSpectrum = ((modelid == 'LST001') or (modelid == 'LLC007'))

    if state.has_key('hue'):
      self.start_setting['hue'] = state['hue']
      self.start_setting['sat'] = state['sat']
      self.hueLast = state['hue']
      self.satLast = state['sat']
    else:
      self.livingwhite = True

    self.logger.debuglog("group %s start settings: %s" % (self.group_id, self.start_setting))

  def request_url_put(self, url, data):
    try:
      response = self.s.put(url, data=data)
      self.logger.debuglog("response: %s" % response)
    except Exception as e:
      # probably a timeout
      self.logger.debuglog("WARNING: Request fo bridge failed")
      pass

