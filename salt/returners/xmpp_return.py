# -*- coding: utf-8 -*-
'''
Return salt data via xmpp

The following fields can be set in the minion conf file::

    xmpp.jid (required)
    xmpp.password (required)
    xmpp.recipient (required)
    xmpp.profile (optional)

Alternative configuration values can be used by prefacing the configuration.
Any values not found in the alternative configuration will be pulled from
the default location::

    xmpp.jid
    xmpp.password
    xmpp.recipient
    xmpp.profile

XMPP settings may also be configured as::

    xmpp:
        jid: user@xmpp.domain.com/resource
        password: password
        recipient: user@xmpp.example.com

    alternative.xmpp:
        jid: user@xmpp.domain.com/resource
        password: password
        recipient: someone@xmpp.example.com

    xmpp_profile:
        jid: user@xmpp.domain.com/resource
        password: password

    xmpp:
        profile: xmpp_profile
        recipient: user@xmpp.example.com

    alternative.xmpp:
        profile: xmpp_profile
        recipient: someone-else@xmpp.example.com

  To use the XMPP returner, append '--return xmpp' to the salt command. ex:

  .. code-block:: bash

    salt '*' test.ping --return xmpp

  To use the alternative configuration, append '--return_config alternative' to the salt command. ex:

    salt '*' test.ping --return xmpp --return_config alternative
'''

# Import python libs
import distutils.version
import logging
import pprint

log = logging.getLogger(__name__)

HAS_LIBS = False
try:
    from sleekxmpp import ClientXMPP as _ClientXMPP
    HAS_LIBS = True
except ImportError:
    class _ClientXMPP(object):
        '''
        Fake class in order not to raise errors
        '''


__virtualname__ = 'xmpp'


def _get_options(ret=None):
    '''
    Get the redis options from salt.
    '''
    if ret:
        ret_config = '{0}'.format(ret['ret_config']) if 'ret_config' in ret else ''
    else:
        ret_config = None

    attrs = {'xmpp_profile': 'profile',
             'from_jid': 'jid',
             'password': 'password',
             'recipient_jid': 'recipient'}

    _options = {}
    for attr in attrs:
        if 'config.option' in __salt__:
            cfg = __salt__['config.option']
            c_cfg = cfg('{0}'.format(__virtualname__), {})
            if ret_config:
                ret_cfg = cfg('{0}.{1}'.format(ret_config, __virtualname__), {})
                if ret_cfg.get(attrs[attr], cfg('{0}.{1}.{2}'.format(ret_config, __virtualname__, attrs[attr]))):
                    _attr = ret_cfg.get(attrs[attr], cfg('{0}.{1}.{2}'.format(ret_config, __virtualname__, attrs[attr])))
                    log.debug('_attr {0}'.format(_attr))
                else:
                    _attr = c_cfg.get(attrs[attr], cfg('{0}.{1}'.format(__virtualname__, attrs[attr])))
            else:
                _attr = c_cfg.get(attrs[attr], cfg('{0}.{1}'.format(__virtualname__, attrs[attr])))
        else:
            cfg = __opts__
            c_cfg = cfg.get('{0}'.format(__virtualname__), {})
            if ret_config:
                ret_cfg = cfg.get('{0}.{1}'.format(ret_config, __virtualname__), {})
                if ret_cfg.get(attrs[attr], cfg.get('{0}.{1}.{2}'.format(ret_config, __virtualname__, attrs[attr]))):
                    _attr = ret_cfg.get(attrs[attr], cfg.get('{0}.{1}.{2}'.format(ret_config, __virtualname__, attrs[attr])))
                else:
                    _attr = c_cfg.get(attrs[attr], cfg.get('{0}.{1}'.format(__virtualname__, attrs[attr])))
            else:
                _attr = c_cfg.get(attrs[attr], cfg.get('{0}.{1}'.format(__virtualname__, attrs[attr])))
        if not _attr:
            _options[attr] = None
            continue
        _options[attr] = _attr

    # If we're using an xmpp_profile
    # pull from_jid and password from there
    if 'xmpp_profile' in _options:
        log.info('Using xmpp.profile {0}'.format(_options['xmpp_profile']))
        if 'config.option' in __salt__:
            creds = cfg(_options['xmpp_profile'])
        else:
            creds = cfg.get(_options['xmpp_profile'])
        if creds:
            _options['from_jid'] = creds.get('xmpp.jid')
            _options['password'] = creds.get('xmpp.password')

    return _options


def __virtual__():
    '''
    Only load this module if right version of sleekxmpp is installed on this minion.
    '''
    if HAS_LIBS:
        import sleekxmpp
        # Certain XMPP functionaility we're using doesn't work with versions under 1.3.1
        sleekxmpp_version = distutils.version.LooseVersion(sleekxmpp.__version__)
        valid_version = distutils.version.LooseVersion('1.3.1')
        if sleekxmpp_version >= valid_version:
            return __virtualname__
    return False


class SendMsgBot(_ClientXMPP):

    def __init__(self, jid, password, recipient, msg):  # pylint: disable=E1002
        # PyLint wrongly reports an error when calling super, hence the above
        # disable call
        super(SendMsgBot, self).__init__(jid, password)

        self.recipient = recipient
        self.msg = msg

        self.add_event_handler('session_start', self.start)

    def start(self, event):
        self.send_presence()

        self.send_message(mto=self.recipient,
                          mbody=self.msg,
                          mtype='chat')

        self.disconnect(wait=True)


def returner(ret):
    '''
    Send an xmpp message with the data
    '''

    _options = _get_options(ret)

    from_jid = _options.get('from_jid')
    password = _options.get('password')
    recipient_jid = _options.get('recipient_jid')

    if not from_jid:
        log.error('xmpp.jid not defined in salt config')
        return

    if not password:
        log.error('xmpp.password not defined in salt config')
        return

    if not recipient_jid:
        log.error('xmpp.recipient not defined in salt config')
        return

    message = ('id: {0}\r\n'
               'function: {1}\r\n'
               'function args: {2}\r\n'
               'jid: {3}\r\n'
               'return: {4}\r\n').format(
                    ret.get('id'),
                    ret.get('fun'),
                    ret.get('fun_args'),
                    ret.get('jid'),
                    pprint.pformat(ret.get('return')))

    xmpp = SendMsgBot(from_jid, password, recipient_jid, message)
    xmpp.register_plugin('xep_0030')  # Service Discovery
    xmpp.register_plugin('xep_0199')  # XMPP Ping

    if xmpp.connect():
        xmpp.process(block=True)
        return True
    return False
