#!/usr/bin/env python

__author__ = 'james.habben'

evolveVersion = '1.6'

import sys
import argparse
if __name__ == '__main__':
    print 'Python Version: ' + sys.version
    print 'Evolve Version: ' + evolveVersion

    argParser = argparse.ArgumentParser(description='Web interface for Volatility Framework.')
    argParser.add_argument('--version', action='version', version='%(prog)s ' + evolveVersion)
    argParser.add_argument('-d', '--dbfolder', help='Optional database location')
    argParser.add_argument('-f', '--file', help='RAM dump to analyze')
    argParser.add_argument('-l', '--local', help='Restrict webserver to serving \'localhost\' only')
    argParser.add_argument('-w', '--webport', help='Port to bind Web Server on', default=8080)
    argParser.add_argument('-r', '--run', help='Give a comma separated list of plugins to run on startup')
    argParser.add_argument('-p', '--profile', help='VOL: Memory profile to use with Volatility')
    argParser.add_argument('--kdbg', help='VOL: Offset of KDBG for faster searching')
    argParser.add_argument('--dtb', help='VOL: Offset of DTB for faster searching')
    argParser.add_argument('--plugins', help='VOL: Path to additional Volatility plugins to use')
    args = argParser.parse_args()
    sys.argv = []

    if not args.file:
        #raise BaseException("RAM dump file is required.")
        print "RAM dump file is required."
        exit()

import os
#import volatility
#import bottle
import sqlite3
import json
import multiprocessing
import hashlib
import re
import urllib

import volatility.constants as constants
import volatility.conf as conf
if __name__ == '__main__':
    print 'Volatility Version: ' + constants.VERSION
    config = conf.ConfObject()
    if args.plugins:
        config.PLUGINS = args.plugins
        #config.update('plugins', args.plugins)

import volatility.registry as registry
import volatility.commands as commands
import volatility.obj as obj
#import volatility.plugins.taskmods as taskmods
import volatility.addrspace as addrspace
#import volatility.utils as utils
#import volatility.renderers as render
#import volatility.plugins as plugins
import volatility.debug
logger = volatility.debug

#from bottle import route, Bottle, run, request

from morphs.BaseMorph import BaseMorph

results = multiprocessing.Queue()

Plugins = dict(plugins=[], hash=0)
profile = ''
def BuildPluginList():
    config.parse_options()
    con = sqlite3.connect(config.OUTPUT_FILE)
    curs = con.cursor()
    curs.execute('select name from sqlite_master where type = \'table\';')
    tables = []
    for tab in curs.fetchall():
        tables.append(tab[0].lower())
    curs.close()
    con.close()
    Plugins['plugins'] = []
    for cmdname in sorted(cmds):
        command = cmds[cmdname]
        if command.is_valid_profile(profile) or cmdname in tables:
            Plugins['plugins'].append({'name':cmdname,'help':command.help(), 'data':0, 'error':'', 'rowcount':0})

def BuildConfigOptsList(cfg):
    optsList = []
    for opt in cfg.optparser.option_list:
        optsList.append(({'name':opt.dest, 'arg':opt.get_opt_string(), 'help':opt.help, 'type':opt.type, 'action':opt.action}))
    return tuple(optsList)

def BuildConfigOpts(plugin='', getDiff=False):
    optsList = BuildConfigOptsList(config)
    if plugin.__len__() > 0:
        config2 = conf.ConfObject()
        cmds[plugin](config2)
        optsList2 = BuildConfigOptsList(config2)
        #set(optsList)
        #set(optsList2)
        return [x for x in optsList2 if x not in optsList]
    else:
        return optsList

def BuildMorphList():
    morphpath = os.path.join(os.path.dirname(__file__), 'morphs')
    for morphfile in os.listdir(morphpath):
        if morphfile.endswith('py') and morphfile.lower() not in ['basemorph.py','__init__.py']:
            print "found morph: " + morphfile
            __import__('morphs.' + morphfile.replace('.py',''))
    Plugins['morphs'] = []
    for sub in BaseMorph.__subclasses__():
        #sub.__init__(sub)
        Plugins['morphs'].append({'name':sub.name, 'display':sub.displayname,'plugins':sub.plugins, 'helptext':sub.helptext})

def UpdatePluginList():
    # Plugin['data']: 0=no data; 1=data; 2=running;
    con = sqlite3.connect(config.OUTPUT_FILE)
    curs = con.cursor()
    curs.execute('select name from sqlite_master where type = \'table\';')
    tables = []
    for tab in curs.fetchall():
        tables.append(tab[0].lower())
    jobs = {}
    while not results.empty():
        #jobs.append(results.get())
        j = results.get()
        jobs = j
    curs.close()
    con.close()
    for cmdname in Plugins['plugins']:
        if cmdname['data'] == 1 and cmdname['name'] not in tables:
            cmdname['data'] = 0
        if cmdname['error'] == '' and cmdname['data'] != 2 and cmdname['name'] in tables:
            cmdname['data'] = 1
        if cmdname['data'] == 2 and cmdname['name'] in jobs.keys():
            cmdname['error'] = jobs[cmdname['name']]
            if cmdname['name'] in tables:
                cmdname['data'] = 1

            else:
                cmdname['data'] = 0


if __name__ == '__main__':
    #print 'Volatility Version: ' + constants.VERSION

    #config = conf.ConfObject()
    #config.update('plugins', args.plugins)
    #config.PLUGINS = args.plugins

    registry.PluginImporter()
    #config = conf.ConfObject()
    registry.register_global_options(config, addrspace.BaseAddressSpace)
    registry.register_global_options(config, commands.Command)
    config.parse_options(False)

    config.LOCATION = 'file://' + args.file
    config.OUTPUT_FILE = args.file + '.sqlite'
    if args.dbfolder:
        print 'Hashing input file...',
        config.OUTPUT_FILE = os.path.join(args.dbfolder, hashlib.md5(open(args.file).read()).hexdigest() + '.sqlite')
        print 'done'

    #check for existing sqlite file and pull configs
    con = sqlite3.connect(config.OUTPUT_FILE)
    curs = con.cursor()
    query = 'create table if not exist metadata (filepath,evolve_ver,vol_ver,pysqlite_ver,sqlite_ver,vol_profile,vol_kdbg,datetime)'

    query = 'create table is not exist plugin_runs (fileptah,evolve_ver,vol_ver,vol_profile,vol_kdbg,datetime,vol_plugin,rowcount,vol_parameters)'

    query = 'select * from metadata'
    try:
        curs.execute(query)
    except Exception as err:
        print err.message

    profs = registry.get_plugin_classes(obj.Profile)
    if args.profile:
        config.PROFILE = args.profile
    else:
        config.PROFILE = 'WinXPSP2x86'
    if config.PROFILE not in profs:
        #raise BaseException("Invalid profile " + config.PROFILE + " selected")
        print 'Invalid profile ' + config.PROFILE + ' selected'
        exit()

    if args.kdbg:
        config.KDBG = args.kdbg
    if args.dtb:
        config.DTB = args.dtb
    #if args.plugins:
    #    config.PLUGINS = args.plugins
    #    config.update('plugins', args.plugins)
    config.parse_options()


    profile = profs[config.PROFILE]()


    cmds = registry.get_plugin_classes(commands.Command, lower = True)
    BuildPluginList()
    BuildMorphList()
    UpdatePluginList()
    
    #print 'Python Version: ' + sys.version
    #print 'Volatility Version: ' + constants.VERSION
    #print 'Evolve Version: ' + evolveVersion


from bottle import route, Bottle, run, request, static_file

@route('/')
def index():
    return static_file('evolve.htm',root='web')

@route('/apilist')
def index():
    return static_file('apilist.htm',root='web')

@route('/web/:path#.+#', name='web')
def static(path):
    return static_file(path, root='web')

@route('/data/plugins')
def ajax_plugins():
    UpdatePluginList()
    return json.dumps(Plugins)

@route('/data/meta')
def evolve_meta():
    meta = {}
    meta['profilename'] = config.PROFILE
    meta['filepath'] = config.LOCATION
    meta['evolveversion'] = evolveVersion
    meta['volversion'] = constants.VERSION
    return json.dumps(meta)

@route('/data/profilelist')
def profile_list():
    plugins = registry.get_plugin_classes(obj.Profile)
    result = []
    for clsname, cls in sorted(plugins.items()):
        try:
            doc = cls.__doc__.strip().splitlines()[0]
        except AttributeError:
            doc = 'No docs'
        result.append((clsname, doc))
    return json.dumps(result)

@route('/data/optslist', method='GET')
@route('/data/optslist/plugin/<name>', method='GET')
def opts_list(name=''):
    request.route
    return json.dumps(BuildConfigOpts(name))

@route('/config/profile/<pname>')
def set_profile(pname):
    global profile
    global cmds
    global config
    config.PROFILE = pname
    profile = profs[config.PROFILE]()
    print 'Set profile to {0}'.format(pname)
    BuildPluginList()
    #UpdatePluginList()

@route('/data/view/<name>', method='GET')
@route('/data/view/<name>', method='POST')
@route('/data/view/<name>/morph/<morph>', method='GET')
@route('/data/view/<name>/morph/<morph>', method='POST')
def plugin_data(name, morph=''):
    result = {'columns':[],'data':[]}
    con = sqlite3.connect(config.OUTPUT_FILE)
    if request.method == 'POST' and request.forms.get('query'):
        query = request.forms.get('query')
    else:
        query = 'SELECT * FROM ' + name
    curs = con.cursor()
    try:
        curs.execute(query)
        result['data'] = curs.fetchall()
        result['columns'] = [i[0] for i in curs.description]
    except Exception as err:
        result['error'] = err.message
    result['name'] = name
    result['query'] = query
    result['morphs'] = []
    for m in Plugins['morphs']:
        if name in m['plugins']:
            result['morphs'].append(m['name'])
    if morph:
        for sub in BaseMorph.__subclasses__():
            if sub.name == morph:
                cls = sub()
                cls.morph(result)

    return json.dumps(result)

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

@route('/data/view/pidprofile/<pid>', method='GET')
def pid_profile(pid):
    con = sqlite3.connect(config.OUTPUT_FILE)
    curs = con.cursor()
    result = {}
    result['name'] = 'PID Profile'
    result['query'] = pid

    result = pull_pid_data('pslist', pid, result)
    result = pull_pid_data('pslist', pid, result, 'pslist-children', 'ppid')
    result = pull_pid_data('dlllist', pid, result)
    result = pull_pid_data('connections', pid, result)
    result = pull_pid_data('connscan', pid, result)
    result = pull_pid_data('sockets', pid, result)
    result = pull_pid_data('socketscan', pid, result)
    result = pull_pid_data('netscan', pid, result)
    result = pull_pid_data('malfind', pid, result)
    result = pull_pid_data('psxview', pid, result)
    result = pull_pid_data('cmdline', pid, result)
    result = pull_pid_data('cmdscan', pid, result)

    return json.dumps(result)

def pull_pid_data(table, value, result, name='', where='pid'):
    con = sqlite3.connect(config.OUTPUT_FILE)
    curs = con.cursor()
    if name == '':
        name = table
    result['datasets'] = []
    result['datasets'] [name] = {'columns': [], 'data': []}
    try:
        curs.execute('select * from ' + table + ' where ' + where + ' = ' + value)
        result['datasets'][name]['data'] = curs.fetchall()
        result['datasets'][name]['columns'] = [i[0] for i in curs.description]
    except Exception as err:
        result['error'] = err.message
    return result

@route('/data2/plugin/<name>')
def plugin_data2(name):
    con = sqlite3.connect(config.OUTPUT_FILE)
    con.row_factory = dict_factory
    cur = con.cursor()
    cur.execute('SELECT * FROM ' + name)
    return json.dumps( cur.fetchall())

@route('/run/plugin/<name>')
def run_plugin(name):
    for cmdname in Plugins['plugins']:
        if cmdname['name'] == name:
            cmdname['data'] = 2 # running
            break
    p = multiprocessing.Process(target=run_plugin_process, kwargs=dict(name=name, queue=results, config=config, cmds=cmds))
    p.daemon = True
    p.start()
    return

@route('/config/morph/<name>', method='GET')
def morph_config(name):
    for sub in BaseMorph.__subclasses__():
        if sub.name.lower() == name.lower():
            cls = sub()
            data = {
                'name':cls.name,
                'display':cls.displayname,
                'helptext':cls.helptext,
                'plugins':cls.plugins,
                'config':cls.config
            }
            return json.dumps(data)

@route('/config/morph/<name>', method='POST')
def morph_set_config(name):
    try:
        for sub in BaseMorph.__subclasses__():
            if sub.name.lower() == name.lower():
                cls = sub()
                #cls.SetConfig(request.forms.dict)
                cls.SetConfig(request.json)
                break
        return json.dumps({'result':'success'})
    except Exception as err:
        print err.message + ': ' + str(err.args)
        return json.dumps({'result':'error','msg':err.message + ': ' + str(err.args)})

# backend function for the jqueryFileTree
@route('/browse/server', method='POST')
def dirlist():
    r = ['<ul class="jqueryFileTree" style="display: none;">']
    try:
        r = ['<ul class="jqueryFileTree" style="display: none;">']
        #d = request.forms.get('dir')
        d = urllib.unquote(request.forms.get('dir'))
        if os.name == 'nt':
            if d == '/':
                drives = re.findall(r"[A-Z]+:.*$",os.popen('mountvol /').read(),re.MULTILINE)
                drives.sort()
                for dr in drives:
                    r.append('<li class="directory collapsed"><a href="#" rel="%s">%s</a></li>' % (dr,dr))
            else:
                for f in os.listdir(d):
                    ff=os.path.join(d,f)
                    if os.path.isdir(ff):
                        r.append('<li class="directory collapsed"><a href="#" rel="%s">%s</a></li>' % (ff,f))
                    else:
                        e=os.path.splitext(f)[1][1:] # get .ext and remove dot
                        r.append('<li class="file ext_%s"><a href="#" rel="%s">%s</a></li>' % (e,ff,f))
        else:
            for f in os.listdir(d):
                ff=os.path.join(d,f)
                if os.path.isdir(ff):
                    r.append('<li class="directory collapsed"><a href="#" rel="%s/">%s</a></li>' % (ff,f))
                else:
                    e=os.path.splitext(f)[1][1:] # get .ext and remove dot
                    r.append('<li class="file ext_%s"><a href="#" rel="%s">%s</a></li>' % (e,ff,f))
        r.append('</ul>')
    except Exception,e:
        r.append('Could not load directory: %s' % str(e))
    r.append('</ul>')
    return r


def run_plugin_process(name, queue, config, cmds):
    registry.PluginImporter()
    registry.register_global_options(config, addrspace.BaseAddressSpace)
    registry.register_global_options(config, commands.Command)
    config.parse_options()
    command = cmds[name](config)
    print 'running: ' + name
    errstr = ''
    try:
        calc = command.calculate()
        command.render_sqlite(config.OUTPUT_FILE, calc)
        #AddColumn(config.OUTPUT_FILE, name, 'profile', config.PROFILE)
    except Exception as err:
        print name + ': ' + err.message
        errstr = err.message
    finally:
        result = {name:errstr}
        queue.put(result)
        #queue.put(name)
    return

def isSQLite3(filename):
    from os.path import isfile, getsize

    if not isfile(filename):
        return False
    if getsize(filename) < 100: # SQLite database file header is 100 bytes
        return False

    with open(filename, 'rb') as fd:
        header = fd.read(100)

    return header[:16] == 'SQLite format 3\x00'


def AddColumn(db, table, column, value):
    con = sqlite3.connect(db)
    cur = con.cursor()
    try:
        cur.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + column + ' TEXT default NULL;')
        cur.close()
        con.close()
        con2 = sqlite3.connect(db)
        cur2 = con2.cursor()
        query = "update {0} set {1} = '{2}' --where {1} is NULL;".format(table, column, value)
        #cur.execute('update ' + table + ' set ' + column + ' = \'' + value + '\' where ' + column + ' is null;')
        cur2.execute(query)
    except:
        pass # handle the error
    cur2.close()
    con2.close()

if __name__ == '__main__':
    if args.run:
        runlist = args.run.split(',')
        for runplug in runlist:
            for plug in Plugins['plugins']:
                if plug['name'] == runplug and plug['data'] == 0:
                    plug['data'] = 2 # running
                    p = multiprocessing.Process(target=run_plugin_process, kwargs=dict(name=runplug, queue=results,))
                    p.daemon = True
                    p.start()

    app = Bottle()
    hostip = '0.0.0.0'
    if args.local:
        hostip = '127.0.0.1'
    run(host=hostip, port=args.webport)

