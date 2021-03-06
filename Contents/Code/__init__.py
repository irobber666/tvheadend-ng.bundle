import urllib2, base64, simplejson, time, pyq
json = simplejson

# Static text. 
TEXT_NAME = 'TV-Headend Next Generation'
TEXT_TITLE = 'TV-Headend' 

# Image resources.
ICON_MAIN = 'main.png'

# Other definitions.
PLUGIN_PREFIX = '/video/tvheadend-ng'
debug = True
debug_epg = False 
debug_gn = False

# Global variables.
gn_thread = False
gn_channels = False
gn_channels_update = 0

####################################################################################################

def Start():
	Plugin.AddPrefixHandler(PLUGIN_PREFIX, MainMenu, TEXT_NAME, ICON_MAIN)
	Plugin.AddViewGroup("InfoList", viewMode="InfoList", mediaType="items")
	Plugin.AddViewGroup("List", viewMode="List", mediaType="items")
	HTTP.CacheTime = 1

	Thread.Create(gracenoteThread, globalize=True)

####################################################################################################

@handler('/video/tvheadend-ng', TEXT_TITLE, thumb=ICON_MAIN)
def MainMenu():
	oc = ObjectContainer(view_group='InfoList', no_cache=True)	

	if checkConfig():
		if debug == True: Log("Configuration OK!")
		oc.title1 = TEXT_TITLE
		oc.header = None
		oc.message = None 
		oc = ObjectContainer(title1=TEXT_TITLE, no_cache=True)
		oc.add(DirectoryObject(key=Callback(getChannels, title=L('allchans')), title=L('allchans')))
		oc.add(DirectoryObject(key=Callback(getChannelsByTag, title=L('tagchans')), title=L('tagchans')))
		oc.add(PrefsObject(title=L('preferences')))
	else:
		if debug == True: Log("Configuration error! Displaying error message...")
		oc.title1 = None
		oc.header = L('header_attention')
                oc.message = L('error_no_config')
		oc.add(PrefsObject(title=L('preferences')))

	return oc

####################################################################################################

def ValidatePrefs():
	if gn_thread == False and Prefs['gracenote_tvlogos'] == True:
		Thread.Create(gracenoteThread, globalize=True)

def gracenoteThread():
	if debug == True: Log("******  Starting gracenote thread  ***********")
	thread_sleep = 60
	global gn_thread
	global gn_channels
	global gn_channels_update

	gn_thread = True

	# Cache TTL (seconds).
	gn_channels_ttl = 300 

	while (Prefs['gracenote_tvlogos'] == True):
		if debug == True: Log.Info("gracenoteThread() loop...")

		json_data = getTVHeadendJson('getChannelGrid', '')
		json_services = getServices()
		json_muxes = getMuxes()
		dvbtriplets = []

		# Fetch dvbids.
		for channel in json_data['entries']:
			# Get DVB ids.
			dvbids = getDVBIDS(channel['services'], json_services, json_muxes)
			dvbtriplets.append({"onid":dvbids['onid'], "tsid":dvbids['tsid'], "sid":dvbids['sid']})

		try:
			# Check if there's already a validated gracenote clientid/userid combination within data cache.
			if not 'gracenote_userid' in Dict or not 'gracenote_clientid' in Dict:
				if debug == True: Log("No valid gracenote clientid/userid combination found within data cache.")
				Dict['gracenote_clientid'] = Prefs['gracenote_clientid']
				Dict['gracenote_userid'] = pyq.register(Prefs['gracenote_clientid'])
				if debug == True: Log("New combination: " + Dict['gracenote_clientid'] + " / " + Dict['gracenote_userid'])
				Dict.Save()
			else:
				if Dict['gracenote_clientid'] != Prefs['gracenote_clientid']:
					if debug == True: Log("Expired gracenote clientid/userid combination found within data cache.")
					Dict['gracenote_clientid'] = Prefs['gracenote_clientid']
					Dict['gracenote_userid'] = pyq.register(Prefs['gracenote_clientid'])
					if debug == True: Log("New combination: " + Dict['gracenote_clientid'] + " / " + Dict['gracenote_userid'])
					Dict.Save()
				else:
					# Try to fetch gracenote data.
					# Only poll after ttl expires.
					if time.time() > gn_channels_update + gn_channels_ttl:
						if debug == True: Log("Gracenote channel TTL expired. Fetching channeldata from gracenote.")
						gn_channels = pyq.lookupChannels(Dict['gracenote_clientid'], Dict['gracenote_userid'], "DVBIDS", dvbtriplets)
						gn_channels_update = time.time()
					else:
						if debug == True: Log("Gracenote channel TTL not reached. Waiting for next poll.")
					if debug_gn == True: Log(gn_channels)
		except Exception, e:
			if debug == True: Log("Talking to gracenote service failed: " + str(e))
			gn_channels = False
			gn_channels_update = 0
			gn_epg = False

		# Let the thread sleep for some seconds.
		if debug == True: Log("****** Gracenote thread sleeping for " + str(thread_sleep) + " seconds ***********")
		Thread.Sleep(float(thread_sleep))
	if debug == True: Log("Exiting gracenote thread....")
	gn_thread = False
	gn_channels = False
	gn_channels_update = 0

def checkConfig():
	if Prefs['tvheadend_user'] != "" and Prefs['tvheadend_pass'] != "" and Prefs['tvheadend_host'] != "" and Prefs['tvheadend_web_port'] != "":
		# To validate the tvheadend connection, the function to fetch the channeltags will be used.
		json_data = getTVHeadendJsonOld('channeltags')
		if json_data != False:
			return True
		else:
			return False
	else:
		return False

def getTVHeadendJsonOld(what, url = False):
	if debug == True: Log("JSON-RequestOld: " + what)
	tvh_url = dict( channeltags='op=listTags', epg='start=0&limit=300')
	if url != False: 
		tvh_url[what] = url

	try:
		base64string = base64.encodestring('%s:%s' % (Prefs['tvheadend_user'], Prefs['tvheadend_pass'])).replace('\n', '')
		request = urllib2.Request("http://%s:%s/%s" % (Prefs['tvheadend_host'], Prefs['tvheadend_web_port'], what),tvh_url[what])
		request.add_header("Authorization", "Basic %s" % base64string)
		response = urllib2.urlopen(request)
		json_tmp = response.read().decode('utf-8')
		json_data = json.loads(json_tmp)
	except Exception, e:
		if debug == True: Log("JSON-RequestOld failed: " + str(e))
		return False	
	if debug == True: Log("JSON-RequestOld successfull!")
	return json_data

def getTVHeadendJson(apirequest, arg1):
	if debug == True: Log("JSON-Request: " + apirequest)
	api = dict(
		getChannelGrid='api/channel/grid?start=0&limit=999999',
		getEpgGrid='api/epg/grid?start=0&limit=1000',
		getIdNode='api/idnode/load?uuid=' + arg1,
		getServiceGrid='api/mpegts/service/grid?start=0&limit=999999',
		getMuxGrid='api/mpegts/mux/grid?start=0&limit=999999'
	)

	try:
                base64string = base64.encodestring('%s:%s' % (Prefs['tvheadend_user'], Prefs['tvheadend_pass'])).replace('\n', '')
                request = urllib2.Request("http://%s:%s/%s" % (Prefs['tvheadend_host'], Prefs['tvheadend_web_port'], api[apirequest]))
                request.add_header("Authorization", "Basic %s" % base64string)
                response = urllib2.urlopen(request)

                json_tmp = response.read().decode('utf-8')
                json_data = json.loads(json_tmp)
	except Exception, e:
		if debug == True: Log("JSON-Request failed: " + str(e))
		return False
	if debug == True: Log("JSON-Request successfull!")
	return json_data

####################################################################################################

def getEPG():
	json_data = getTVHeadendJson('getEpgGrid','')
	if json_data != False:
		if debug_epg == True: Log("Got EPG: " + json.dumps(json_data))
	else:
		if debug_epg == True: Log("Failed to fetch EPG!")	

	return json_data

def getServices():
	json_data = getTVHeadendJson('getServiceGrid','')
	return json_data

def getMuxes():
	json_data = getTVHeadendJson('getMuxGrid','')
	return json_data

def getDVBIDS(chan_services, json_services, json_muxes):
	result = {
		'sid':'',
		'onid':'',
		'tsid':''
	}

	# Loop through given services.
	for chan_service in chan_services:

		# Loop through all fetched services.
		for service in json_services['entries']:

			# Check if the the given service of a channel is found within the servicelist.
			if service['uuid'] == chan_service:

				# Loop through all muxes.
				for mux in json_muxes['entries']:

					# Check if the network and name match for service. 
					if mux['name'] == service['multiplex'] and mux['network'] == service['network']:
						result['sid'] = str(service['sid'])
						result['onid'] = str(mux['onid'])
						result['tsid'] = str(mux['tsid'])
	return result

def getChannelLogoFromGracenote(channel):
	if gn_channels != False:
		for gn in gn_channels:
			if gn['name'] == channel:
				return gn['logo_url']
	return False

def getChannelInfo(uuid, services, json_epg):
	result = {
		'iconurl':'',
		'epg_title':'',
		'epg_description':'',
		'epg_duration':0,
		'epg_start':0,
		'epg_stop':0,
		'epg_summary':'',
	}

	json_data = getTVHeadendJson('getIdNode', uuid)
	if json_data['entries'][0]['params'][2].get('value'):
		result['iconurl'] = json_data['entries'][0]['params'][2].get('value')

	# Check if we have data within the json_epg object.
	if json_epg != False and json_epg.get('events'):
		for epg in json_epg['events']:
			if epg['channelUuid'] == uuid and time.time() > int(epg['start']) and time.time() < int(epg['stop']):
				if epg.get('title'):
					 result['epg_title'] = epg['title'];
				if epg.get('description'):
					 result['epg_description'] = epg['description'];
				if epg.get('duration'):
					result['epg_duration'] = epg['duration']*1000;
				if epg.get('start'):
					result['epg_start'] = time.strftime("%H:%M", time.localtime(int(epg['start'])));
				if epg.get('stop'):
					result['epg_stop'] = time.strftime("%H:%M", time.localtime(int(epg['stop'])));
	return result

####################################################################################################

def getChannelsByTag(title):
	json_data = getTVHeadendJsonOld('channeltags')
	tagList = ObjectContainer(no_cache=True)

	if json_data != False:
		tagList.title1 = L('tagchans')
		tagList.header = None
		tagList.message = None
		for tag in sorted(json_data['entries'], key=lambda t: t['name']):
			if debug == True: Log("Getting channellist for tag: " + tag['name'])
			tagList.add(DirectoryObject(key=Callback(getChannels, title=tag['name'], tag=int(tag['identifier'])), title=tag['name']))
	else:
		if debug == True: Log("Could not create tagelist! Showing error.")
		tagList.title1 = None
		tagList.header = L('error')
		tagList.message = L('error_request_failed') 

	if debug == True: Log("Count of configured tags within TV-Headend: " + str(len(tagList)))
	if ( len(tagList) == 0 ):
		tagList.header = L('attention')
		tagList.message = L('error_no_tags')
	return tagList 

def getChannels(title, tag=int(0)):
	json_data = getTVHeadendJson('getChannelGrid', '')
	json_epg = getEPG()
	channelList = ObjectContainer(no_cache=True)

	if json_data != False:
		channelList.title1 = title
		channelList.header = None
		channelList.message = None
		for channel in sorted(json_data['entries'], key=lambda t: t['number']):
			if tag > 0:
				tags = channel['tags']
				for tids in tags:
					if (tag == int(tids)):
						if debug == True: Log("Got channel with tag: " + channel['name'])
						chaninfo = getChannelInfo(channel['uuid'], channel['services'], json_epg)
						channelList.add(createTVChannelObject(channel, chaninfo, Client.Product, Client.Platform))
			else:
				chaninfo = getChannelInfo(channel['uuid'], channel['services'], json_epg)
				channelList.add(createTVChannelObject(channel, chaninfo, Client.Product, Client.Platform))
	else:
		if debug == True: Log("Could not create channellist! Showing error.")
		channelList.title1 = None;
		channelList.header = L('error')
		channelList.message = L('error_request_failed')
       	return channelList

def createTVChannelObject(channel, chaninfo, cproduct, cplatform, container = False):
	if debug == True: Log("Creating TVChannelObject. Container: " + str(container))
	name = channel['name'] 
	icon = ""
	if chaninfo['iconurl'] != "":
		icon = chaninfo['iconurl']
	id = channel['uuid'] 
	summary = ''
	duration = 0

	# Handle gracenote data.
	gn_logo = getChannelLogoFromGracenote(name)
	if gn_logo != False:
		if debug == True: Log("Adding gracenote channel logo for channel: " + name)
		icon = gn_logo 

	# Add epg data. Otherwise leave the fields blank by default.
	if chaninfo['epg_title'] != "" and chaninfo['epg_start'] != 0 and chaninfo['epg_stop'] != 0 and chaninfo['epg_duration'] != 0:
		if container == False:
			name = name + " (" + chaninfo['epg_title'] + ") - (" + chaninfo['epg_start'] + " - " + chaninfo['epg_stop'] + ")"
			summary = ""
		if container == True:
			summary = chaninfo['epg_title'] + "\n" + chaninfo['epg_start'] + " - " + chaninfo['epg_stop'] + "\n\n" + chaninfo['epg_description'] 
		duration = chaninfo['epg_duration']
		#summary = '%s (%s-%s)\n\n%s' % (chaninfo['epg_title'],chaninfo['epg_start'],chaninfo['epg_stop'], chaninfo['epg_description'])

	# Build streaming url.
	url_structure = 'stream/channel'
	url_base = 'http://%s:%s@%s:%s/%s/' % (Prefs['tvheadend_user'], Prefs['tvheadend_pass'], Prefs['tvheadend_host'], Prefs['tvheadend_web_port'], url_structure)
	url_transcode = '?mux=mpegts&acodec=aac&vcodec=H264&transcode=1'
	vurl = url_base + id + url_transcode

	# Create raw VideoClipObject.
	vco = VideoClipObject(
		key = Callback(createTVChannelObject, channel = channel, chaninfo = chaninfo, cproduct = cproduct, cplatform = cplatform, container = True),
		rating_key = id,
		title = name,
		summary = summary,
		duration = duration,
		thumb = icon,
	)

	# Decide if we have to stream for Plex Home Theatre or devices with H264/AAC support. 
	if cproduct != "Plex Home Theater" and cproduct != "PlexConnect":
		# Create media object for a 576px resolution.
		mo384 = MediaObject(
			container = 'mpegts',
			video_codec = VideoCodec.H264,
			audio_codec = AudioCodec.AAC,
			audio_channels = 2,
			optimized_for_streaming = False,
			video_resolution = 384,
			parts = [PartObject(key = vurl + "&resolution=384")]
		)
		vco.add(mo384)
		if debug == True: Log("Creating MediaObject with vertical resolution: 384")
		if debug == True: Log("Providing Streaming-URL: " + vurl + "&resolution=384")

		# Create media object for a 576px resolution.
		mo576 = MediaObject(
			container = 'mpegts',
			video_codec = VideoCodec.H264,
			audio_codec = AudioCodec.AAC,
			audio_channels = 2,
			optimized_for_streaming = False,
			video_resolution = 576,
			parts = [PartObject(key = vurl + "&resolution=576")]
		)
		if debug == True: Log("Creating MediaObject with vertical resolution: 576")
		if debug == True: Log("Providing Streaming-URL: " + vurl + "&resolution=576")
		vco.add(mo576)

		# Create mediaobjects for hd tv-channels.
		if channel['name'].endswith('HD'):
			mo768 = MediaObject(
				container = 'mpegts',
				video_codec = VideoCodec.H264,
				audio_codec = AudioCodec.AAC,
				audio_channels = 2,
				optimized_for_streaming = False,
				video_resolution = 768,
				parts = [PartObject(key = vurl + "&resolution=768")]
			)
			mo1080 = MediaObject(
				container = 'mpegts',
				video_codec = VideoCodec.H264,
				audio_codec = AudioCodec.AAC,
				audio_channels = 2,
				optimized_for_streaming = False,
				video_resolution = 1080,
				parts = [PartObject(key = vurl)]
			)
			vco.add(mo768)
			if debug == True: Log("Creating MediaObject with vertical resolution: 768")
			if debug == True: Log("Providing Streaming-URL: " + vurl + "&resolution=768")
			vco.add(mo1080)
			if debug == True: Log("Creating MediaObject with vertical resolution: 1080")
			if debug == True: Log("Providing Streaming-URL: " + vurl + "&resolution=1080")
	else:
		# Create mediaobjects for native streaming.
		if Client.Product == "Plex Home Theater":
			monat = MediaObject(
				optimized_for_streaming = False,
				parts = [PartObject(key = url_base + id)]
			)
			vco.add(monat)
			if debug == True: Log("Creating MediaObject for native streaming")
			if debug == True: Log("Providing Streaming-URL: " + url_base + id)
		else:
			monat = MediaObject(
				optimized_for_streaming = False,
				parts = [PartObject(key = url_base + id + '?mux=mpegts&transcode=1')]
			)
			vco.add(monat)
			if debug == True: Log("Creating MediaObject for newly muxed streaming")
			if debug == True: Log("Providing Streaming-URL: " + url_base + id + '?mux=mpegts&transcode=1')

	if debug == True: Log("Created VideoObject for plex product: " + cproduct + " on " + cplatform)

	if container:
		return ObjectContainer(objects = [vco])
	else:
		return vco
	return vco
