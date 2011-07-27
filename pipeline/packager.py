import os
import urlparse

from pipeline.conf import settings
from pipeline.compilers import Compiler
from pipeline.compressors import Compressor
from pipeline.glob import glob
from pipeline.signals import css_compressed, js_compressed
from pipeline.storage import storage
from pipeline.versioning import Versioning


class Packager(object):
    def __init__(self, force=False, verbose=False):
        self.force = force
        self.verbose = verbose
        self.compressor = Compressor(verbose)
        self.versioning = Versioning(verbose)
        self.compiler = Compiler(verbose)
        self.packages = {
            'css': self.create_packages(settings.PIPELINE_CSS),
            'js': self.create_packages(settings.PIPELINE_JS),
        }

    def package_for(self, kind, package_name):
        try:
            return self.packages[kind][package_name].copy()
        except KeyError:
            raise PackageNotFound(
                "No corresponding package for %s package name : %s" % (
                    kind, package_name
                )
            )

    def individual_url(self, filename):
        return urlparse.urljoin(settings.PIPELINE_URL,
            self.compressor.relative_path(filename)[1:])

    def pack_stylesheets(self, package):
        variant = package.get('variant', None)
        return self.pack(package, self.compressor.compress_css, css_compressed,
            variant=variant)

    def compile(self, paths):
        return self.compiler.compile(paths)

    def pack(self, package, compress, signal, **kwargs):
        if settings.PIPELINE_AUTO or self.force:
            need_update, version = self.versioning.need_update(
                package['output'], package['paths'])
            if need_update or self.force:
                output_filename = self.versioning.output_filename(package['output'],
                    self.versioning.version(package['paths']))
                self.versioning.cleanup(package['output'])
                if self.verbose or self.force:
                    print "Version: %s" % version
                    print "Saving: %s" % output_filename
                paths = self.compile(package['paths'])
                content = compress(paths,
                    asset_url=self.individual_url(output_filename), **kwargs)
                self.save_file(output_filename, content)
                signal.send(sender=self, package=package, version=version)
        else:
            filename_base, filename = os.path.split(package['output'])
            version = self.versioning.version_from_file(filename_base, filename)
        return self.versioning.output_filename(package['output'], version)

    def pack_javascripts(self, package):
        return self.pack(package, self.compressor.compress_js, js_compressed, templates=package['templates'])

    def pack_templates(self, package):
        return self.compressor.compile_templates(package['templates'])

    def save_file(self, path, content):
        file = storage.open(path, 'wb')
        file.write(content)
        file.close()
        return path

    def create_packages(self, config):
        packages = {}
        if not config:
            return packages
        for name in config:
            packages[name] = {}
            if 'external_urls' in config[name]:
                packages[name]['externals'] = config[name]['external_urls']
                continue
            paths = []
            for pattern in config[name]['source_filenames']:
                for path in glob(pattern):
                    if not path in paths:
                        paths.append(str(path))
            packages[name]['paths'] = [path for path in paths if not path.endswith(settings.PIPELINE_TEMPLATE_EXT)]
            packages[name]['templates'] = [path for path in paths if path.endswith(settings.PIPELINE_TEMPLATE_EXT)]
            packages[name]['output'] = config[name]['output_filename']
            packages[name]['context'] = {}
            packages[name]['manifest'] = True
            if 'extra_context' in config[name]:
                packages[name]['context'] = config[name]['extra_context']
            if 'template_name' in config[name]:
                packages[name]['template'] = config[name]['template_name']
            if 'variant' in config[name]:
                packages[name]['variant'] = config[name]['variant']
            if 'manifest' in config[name]:
                packages[name]['manifest'] = config[name]['manifest']                
        return packages


class PackageNotFound(Exception):
    pass
