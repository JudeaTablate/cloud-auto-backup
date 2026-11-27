"""cloud-auto-backup: snapshot a directory and send it up to the cloud.

The pipeline is deliberately small:

    config  ->  archive  ->  remote.upload  ->  retention.prune
"""

__version__ = "2.0.0"
