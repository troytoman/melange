#!/usr/bin/env python

# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

#import optparse

#from melange import ipv4
#from melange import mac
#from melange.common import config
from melange.db import db_api
from melange.db.sqlalchemy import session


def upgrade(migrate_engine):
    interface = session.get_session().execute(
        "SELECT COUNT(1) as count FROM interfaces "
        "WHERE device_id NOT REGEXP '.*-.*' AND device_id IS NOT NULL")
    print(interface)
    if interface.fetchone().count > 0:
        print """
---------------------------------------------------------
You have instances IDs stored in your interfaces table. You need to run this
migration with a connection url for your Nova database. It will extract the
proper UUIDs from the Nova DB and update this table. Using devstack this would
look like:

$ python melange/db/sqlalchemy/migrate_repo/versions/002_device_id_to_uuid.py\\
     -vd --config-file=/opt/stack/melange/etc/melange/melange.conf\\
     mysql://root:password@localhost/nova

---------------------------------------------------------
"""

    # check for uuids in interfaces.device_id


def downgrade(migrate_engine):
    pass

if __name__ == '__main__':
    import gettext
    import optparse
    import os
    import sys

    gettext.install('melange', unicode=1)

    possible_topdir = os.path.normpath(os.path.join(
                                         os.path.abspath(sys.argv[0]),
                                         os.pardir,
                                         os.pardir,
                                         os.pardir,
                                         os.pardir,
                                         os.pardir,
                                         os.pardir))
    if os.path.exists(os.path.join(possible_topdir, 'melange', '__init__.py')):
        sys.path.insert(0, possible_topdir)

    from melange import ipv4
    from melange import mac
    from melange.common import config
    from melange.db import db_api
    from melange.ipam import models
    from melange.db.sqlalchemy import session
    from melange.openstack.common import config as openstack_config

    oparser = optparse.OptionParser()
    openstack_config.add_common_options(oparser)
    openstack_config.add_log_options(oparser)
    (options, args) = openstack_config.parse_options(oparser)

    if len(args) < 1:
        sys.exit("Please include the connection string for the nova DB")

    try:
        conf = config.load_app_environment(optparse.OptionParser())
        db_api.configure_db(conf, ipv4.plugin(), mac.plugin())
        nova_engine = session._create_engine({'sql_connection': args[0]})
        instances = nova_engine.execute("select id,uuid from instances")
        melange_session = session.get_session()

        print "-----"
        for instance in instances:
            print "updating %(id)s with %(uuid)s" % instance
            session._ENGINE.execute("update interfaces set "
                                    "device_id='%(uuid)s' "
                                    "where device_id=%(id)s" % instance)

    except RuntimeError as error:
        sys.exit("ERROR: %s" % error)
