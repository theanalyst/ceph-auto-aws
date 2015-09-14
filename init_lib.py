#
# init_lib.py
#
# functions for initialization
#

from aws_lib import SpinupError
import base64
from boto import vpc, ec2
from os import environ
from pprint import pprint
import re
import time
from yaml_lib import yaml_attr


def read_user_data( fn ):
    """
        Given a filename, returns the file's contents in a string.
    """
    r = ''
    with open( fn ) as fh: 
        r = fh.read()
        fh.close()
    return r


def get_tags( ec, r_id ):
    """
        Takes EC2Connection object and resource ID. Returns tags associated
        with that resource.
    """
    return ec.get_all_tags(filters={ "resource-id": r_id })


def get_tag( ec, obj, tag ):
    """
        Get the value of a tag associated with the given resource object.
        Returns None if the tag is not set. Warning: EC2 tags are case-sensitive.
    """
    tags = get_tags( ec, obj.id )
    found = 0
    for t in tags:
        if t.name == tag:
            found = 1
            break
    if found:
        return t
    else:
        return None


def update_tag( obj, tag, val ):
    """
        Given an EC2 resource object, a tag and a value, updates the given tag 
        to val.
    """
    obj.add_tag( tag, val )
    return None


def init_region( r ):
    """
        Takes a region string. Connects to that region.  Returns EC2Connection
        and VPCConnection objects in a tuple.
    """
    # connect to region
    c = vpc.connect_to_region( r )
    ec = ec2.connect_to_region( r )
    return ( c, ec )


def init_vpc( c, cidr ):
    """
        Takes VPCConnection object (which is actually a connection to a
        particular region) and a CIDR block string. Looks for our VPC in that
        region.  Returns the VpcId of our VPC.
    """
    # look for our VPC
    all_vpcs = c.get_all_vpcs()
    found = 0
    our_vpc = None
    for v in all_vpcs:
        if v.cidr_block == cidr:
            our_vpc = v
            found = 1
            break
    if not found:
        raise SpinupError( "VPC {} not found".format(cidr) )

    return our_vpc


def init_subnet( c, cidr ):
    """
        Takes VPCConnection object, which is actually a connection to a
        region, and a CIDR block string. Looks for our subnet in that region.
        Returns the subnet resource object.
    """
    # look for our VPC
    all_subnets = c.get_all_subnets()
    found = 0
    our_subnet = None
    for s in all_subnets:
        if s.cidr_block == cidr:
            our_subnet = s
            found = 1
            break
    if not found:
        SpinupError( "Subnet {} not found".format(s.id) )

    return our_subnet


def set_subnet_map_public_ip( ec, subnet_id ):
    """
        Takes ECConnection object and SubnetId string. Attempts to set the
        MapPublicIpOnLaunch attribute to True.
        FIXME: give credit to source
    """
    orig_api_version = ec.APIVersion
    ec.APIVersion = '2014-06-15'
    ec.get_status(
        'ModifySubnetAttribute',
        {'SubnetId': subnet_id, 'MapPublicIpOnLaunch.Value': 'true'},
        verb='POST'
    )
    ec.APIVersion = orig_api_version

    return None

 
def get_master_instance( ec2_conn, subnet_id ):
    """
        Given EC2Connection object and Master Subnet id, check that there is
        just one instance running in that subnet - this is the Master. Raise
        exception if the number of instances is != 0. 
        Return the Master instance object.
    """
    instances = ec2_conn.get_only_instances( filters={ "subnet-id": subnet_id } )
    if 1 > len(instances):
        raise SpinupError( "There are no instances in the master subnet" )
    if 1 < len(instances):
        raise SpinupError( "There are too many instances in the master subnet" )
    return instances[0]


def template_token_subst( buf, key, val ):
    """
        Given a string (buf), a key (e.g. '@@MASTER_IP@@') and val, replace all
        occurrences of key in buf with val. Return the new string.
    """
    targetre = re.compile( re.escape( key ) )

    return re.sub( targetre, str(val), buf )


def process_user_data( fn, *vars ):
    """
        Given filename of user-data file and a list of environment
        variable names, replaces @@...@@ tokens with the values of the
        environment variables.  Returns the user-data string on success
        raises exception on failure.
    """
    # Get user_data string.
    buf = read_user_data( fn )
    for e in vars:
        if e not in environ:
            raise SpinupError( "Missing environment variable {}!".format( e ) )
        buf = template_token_subst( buf, '@@'+e+'@@', environ[e] )
    return buf


def make_reservation( ec, ami_id, count, **kwargs ):
    """
        Given EC2Connection object, AMI ID, count, as well as all the kwargs
        referred to below, make reservations for count instances and return the
        registration object.
    """
    our_kwargs = { 
        "key_name": kwargs['key_name'],
        "subnet_id": kwargs['subnet_id'],
        "instance_type": kwargs['instance_type'],
        "min_count": count,
        "max_count": count
    }

    # Master or minion?
    if kwargs['master']:
        our_kwargs['user-data'] = kwargs['user-data']
    else:
        # substitute @@MASTER_IP@@ and @@DELEGATE@@
        u = kwargs['user-data']
        u = template_token_subst( u, '@@MASTER_IP@@', kwargs['master-ip'] )
        u = template_token_subst( u, '@@DELEGATE@@', str(delegate) )
        our_kwargs['user-data'] = u

    # Make the reservation.
    reservation = ec.run_instances( ami_id, kwargs )

    # Return the reservation object.
    return reservation


def wait_for_running( ec2_conn, instance_id ):
    """
        Given an instance id, wait for its state to change to "running".
    """
    print "Waiting for {} running state".format( instance_id )
    while True:
        instances = ec2_conn.get_only_instances( instance_ids=[ instance_id ] )
        print "Current state is {}".format( instances[0].state )
        if instances[0].state != 'running':
            print "Sleeping for 5 seconds"
            time.sleep(5)
        else:
            break


def wait_for_available( ec2_conn, volume_id ):
    """
        Given a volume id, wait for its state to change to "available".
    """
    print "Waiting for {} available state".format( volume_id )
    while True:
        volumes = ec2_conn.get_all_volumes( volume_ids=[ volume_id ] )
        print "Current status is {}".format( volumes[0].status )
        if volumes[0].status != 'available':
            print "Sleeping for 5 seconds"
            time.sleep(5)
        else:
            break


