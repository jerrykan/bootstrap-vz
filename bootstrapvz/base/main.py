"""Main module containing all the setup necessary for running the bootstrapping process
.. module:: main
"""

import logging
log = logging.getLogger(__name__)


def main():
	"""Main function for invoking the bootstrap process

	Raises:
		Exception
	"""
	# Get the commandline arguments
	opts = get_opts()
	# Require root privileges, except when doing a dry-run where they aren't needed
	import os
	if os.geteuid() != 0 and not opts['--dry-run']:
		raise Exception('This program requires root privileges.')

	import log
	# Log to file unless --log is a single dash
	if opts['--log'] != '-':
		# Setup logging
		if not os.path.exists(opts['--log']):
			os.makedirs(opts['--log'])
		log_filename = log.get_log_filename(opts['MANIFEST'])
		logfile = os.path.join(opts['--log'], log_filename)
	else:
		logfile = None
	log.setup_logger(logfile=logfile, debug=opts['--debug'])

	# Everything has been set up, begin the bootstrapping process
	run(opts)


def get_opts():
	"""Creates an argument parser and returns the arguments it has parsed
	"""
	from docopt import docopt
	usage = """bootstrap-vz

Usage: bootstrap-vz [options] MANIFEST

Options:
  --log <path>       Log to given directory [default: /var/log/bootstrap-vz]
                     If <path> is `-' file logging will be disabled.
  --pause-on-error   Pause on error, before rollback
  --dry-run          Don't actually run the tasks
  --debug            Print debugging information
  -h, --help         show this help
	"""
	opts = docopt(usage)
	return opts


def run(opts):
	"""Runs the bootstrapping process

	Args:
		opts (dict): Dictionary of options from the commandline
	"""
	# Load the manifest
	from manifest import Manifest
	manifest = Manifest(opts['MANIFEST'])

	# Get the tasklist
	from tasklist import TaskList
	tasklist = TaskList()
	# 'resolve_tasks' is the name of the function to call on the provider and plugins
	tasklist.load('resolve_tasks', manifest)

	# Create the bootstrap information object that'll be used throughout the bootstrapping process
	from bootstrapinfo import BootstrapInformation
	bootstrap_info = BootstrapInformation(manifest=manifest, debug=opts['--debug'])

	try:
		# Run all the tasks the tasklist has gathered
		tasklist.run(info=bootstrap_info, dry_run=opts['--dry-run'])
		# We're done! :-)
		log.info('Successfully completed bootstrapping')
	except (Exception, KeyboardInterrupt) as e:
		# When an error occurs, log it and begin rollback
		log.exception(e)
		if opts['--pause-on-error']:
			# The --pause-on-error is useful when the user wants to inspect the volume before rollback
			raw_input('Press Enter to commence rollback')
		log.error('Rolling back')

		# Create a new tasklist to gather the necessary tasks for rollback
		rollback_tasklist = TaskList()

		# Create a useful little function for the provider and plugins to use,
		# when figuring out what tasks should be added to the rollback list.
		def counter_task(task, counter):
			"""counter_task() adds the second argument to the rollback tasklist
			if the first argument is present in the list of completed tasks

			Args:
				task (Task): The task to look for in the completed tasks list
				counter (Task): The task to add to the rollback tasklist
			"""
			if task in tasklist.tasks_completed and counter not in tasklist.tasks_completed:
				rollback_tasklist.tasks.add(counter)
		# Ask the provider and plugins for tasks they'd like to add to the rollback tasklist
		# Any additional arguments beyond the first two are passed directly to the provider and plugins
		rollback_tasklist.load('resolve_rollback_tasks', manifest, counter_task)

		# Run the rollback tasklist
		rollback_tasklist.run(info=bootstrap_info, dry_run=opts['--dry-run'])
		log.info('Successfully completed rollback')
		raise e
