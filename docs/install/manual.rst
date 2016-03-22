.. _manual_installation:

Manual installation of OiRA
===========================

OiRA is implemented as a set of add-on products for `Plone`_. The
requirements for running an OiRA site are:

* Plone 4.3 or later.
* a SQL database
* two separate virtual hosts

Development files required on the host operating system:

* libffi (Foreign Function Interface library development files)

e.g. on Debian/Ubuntu: ``sudo apt-get install libffi-dev``

Plone installation
------------------

Since OiRA can only run on top of Plone, the installation configuration for the
client and admin interface is based on a `Plone buildout`_. The following listing
shows the packages that must be present in the *eggs* section of the
``buildout.cfg`` configuration file::


  [buildout]
  ...
  eggs =
      Pillow
      osha.oira

This will instruct Plone to install the OiRA software (and Euphorie on which it is based).
Next you will need to add some *zcml* entries to load the necessary configuration as well::

  [instance]
  ...
  zcml =
      osha.oira
      osha.oira-overrides
      euphorie.deployment-meta
      euphorie.deployment
      euphorie.deployment-overrides

After making these two changes you must (re)run buildout and restart your Zope
instance. Navigate to your ``zinstance`` directory and type::

    $ bin/buildout
    $ bin/instance restart

A new *Euphorie website* option should now appear in the list of add-on products
in your Plone control panel. Installing this will setup Euphorie in your site.
Addtionally you will then need to install the package "osha.oira" to get the
OiRA-specific customisations.

For more information on installing add-on products in your Plone site please
see the article `installing an add-on product`_ in the Plone knowledge base.

Configuration
-------------

Euphorie uses `z3c.appconfig <http://pypi.python.org/pypi/z3c.appconfig>`_ to
handle application configuration. All values are stored in the ``euphorie``
section. For example::

  [euphorie]
  client=http://oira.example.com

You need to tell buildout where to find this configuration::

  environment-vars =
    APPCONFIG ${buildout:directory}/etc/euphorie.ini

Some notable options are:

   +----------------------------+------------------------------------------------+
   |options                     | Description                                    |
   +============================+================================================+
   |``client``                  | URL for the client (see also                   |
   |                            | `Virtual hosting`_).                           |
   +----------------------------+------------------------------------------------+
   |``library``                 | Path (inside Plone) to a sectors that          |
   |                            | should be used as the Library of OiRA  tools.  |
   +----------------------------+------------------------------------------------+
   |``max_login_attempts``      | Number: after how many failed login attempts   |
   |                            | in the client the user account gets locked.    |
   +----------------------------+------------------------------------------------+
   |``allow_guest_accounts``    | Boolean: If enabled the feature for guest      |
   |                            | login is available in the client.              |
   +----------------------------+------------------------------------------------+
   |``allow_user_defined_risks``| Boolean: If enabled the feature for creating   |
   |                            | custom riks is available in the client.        |
   +----------------------------+------------------------------------------------+
   |``smartprintng_url``        | URL (including port) of the service used for   |
   |                            | creating PDF prints                            |
   |                            | (see also `PDF printing`_).                    |
   +----------------------------+------------------------------------------------+

Google analytics
----------------

Euphorie includes complete Google Analytics support. However due to data protection
regulations, this feature is not available in OiRA.

Web analytics (Piwik)
---------------------

`Plone by default can be configured <http://docs.plone.org/adapt-and-extend/config/site.html>`_
to include on every page a block of Javascript code for logging information to a
web analytics tool such as Piwik. The OiRA client and admin interface make use of
this option. That means to enable Piwik tracking, the appropriate Javascript (available)
from the Piwik installation) needs to be pasted into the field "Javascript for
web statistics support" of the Plone installation.




SQL database
------------

OIRA uses a SQL database to store information for users of the client. Any
SQL database supported by SQLALchemy_ should work. If you have selected a
database you will need to configure it in ``buildout.cfg``. For example if
you use postgres you will first need to make sure that the psycopg_ driver
is installed by adding it to the *eggs* section::

  [buildout]
  ...
  eggs =
      osha.oira
      psycopg2

next you need to configure the database connection information. This requires
a somewhat verbose statement in the *instance* section of ``buildout.cfg``::

  [instance]
  zcml-additional =
     <configure xmlns="http://namespaces.zope.org/zope"
                xmlns:db="http://namespaces.zope.org/db">
         <include package="z3c.saconfig" file="meta.zcml" />
         <db:engine name="session" url="postgres:///euphorie" />
         <db:session engine="session" />
     </configure>

Make sure The ``url`` parameter is correct for the database you want to use.
It uses the standard SQLAlchemy connection URI format.

To setup the database you must run buildout and run the database initialisation
command::

    $ bin/buildout
    $ bin/instance initdb


Virtual hosting
---------------

Euphorie requires two separate virtual hosts: one host for the client, and one
for CMS tasks. It is common to use ``client.oiraexample.com`` as hostname for the
client and ``admin.oiraexample.com`` as hostname for the CMS. The standard
method for configuring virtual hosting for Plone sites apply here as well. Here
is an example nginx configuration::

  server {
      listen *:80;
      server_name admin.oiraexample.com;

      proxy_read_timeout 360;
      client_max_body_size 50m;
      proxy_set_header Host $http_host;

        location ~ ^(.*)$ {
            rewrite ^(.*)$ /VirtualHostBase/$scheme/admin.oiraexample.com:$server_port/Plone2/VirtualHostRoot$1;
            proxy_pass http://localhost:8002;
            break;
        }
  }

  server {
      listen *:80;
      server_name client.oiraexample.com;

      proxy_read_timeout 360;
      client_max_body_size 50m;
      proxy_set_header Host $http_host;

      proxy_read_timeout 360;
      client_max_body_size 50m;
      proxy_set_header Host $http_host;

      location ~ ^/$ {
          # override to make the redirect work for the start page
          proxy_set_header Host admin.oiraexample.com;
          rewrite ^/$ /documents/en/homepage/ break;
          proxy_pass https://admin.oiraexample.com;
      }

      location ~ ^(.*)$ {
          rewrite ^(.*)$ /VirtualHostBase/$scheme/client.oiraexample.com:$server_port/Plone2/client/VirtualHostRoot$1;
          proxy_pass http://localhost:8002;
          break;
      }
    }



You will also need to configure the URL for the client in the ``euphorie.ini`` file::

  [euphorie]
  client=http://client.oiraexample.com

PDF printing
------------

For creating nicely formatted PDF reports in the client, the external component
`zopyx.smartprintng.server`_ is used. It makes the PDF converting functionality
of `Prince XML`_ available via a web server. The URL of this service must be present
in `euphorie.ini`::

  [euphorie]
  smartprintng_url=http://123.45.67.89:6543





.. _Plone: http://plone.org/
.. _Plone buildout: http://docs.plone.org/4/en/old-reference-manuals/buildout/index.html
.. _download: http://plone.org/download
.. _installing an add-on product: http://docs.plone.org/4/en/manage/installing/installing_addons.html
.. _SQLAlchemy: http://www.sqlalchemy.org/
.. _psycopg: http://initd.org/psycopg/
.. _zopyx.smartprintng.server: https://pypi.python.org/pypi/zopyx.smartprintng.server
.. _Prince XML: http://www.princexml.com/

