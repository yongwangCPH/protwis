from django.db import models


class Protein(models.Model):
    parent = models.ForeignKey('self', null=True)
    family = models.ForeignKey('ProteinFamily')
    species = models.ForeignKey('Species')
    source = models.ForeignKey('ProteinSource')
    residue_numbering_scheme = models.ForeignKey('residue.ResidueNumberingScheme')
    sequence_type = models.ForeignKey('ProteinSequenceType')
    accession = models.CharField(max_length=100)
    entry_name = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    sequence = models.TextField()
    web_link = models.ManyToManyField('common.WebLink')
    
    # non-database attributes
    identity = False # % identity to a reference sequence in an alignment
    similarity = False # % similarity to a reference sequence in an alignment (% BLOSUM62 score > 0)
    similarity_score = False # similarity score to a reference sequence in an alignment (sum of BLOSUM62 scores)
    alignment = False # residues formatted for use in an Alignment class

    def __str__(self):
        return self.entry_name
    
    class Meta():
        db_table = 'protein'


class Gene(models.Model):
    proteins = models.ManyToManyField('Protein')
    species = models.ForeignKey('Species')
    name = models.CharField(max_length=100)
    position = models.SmallIntegerField()

    def __str__(self):
        return self.name

    class Meta():
        ordering = ('position', )
        db_table = 'gene'


class Species(models.Model):
    latin_name = models.CharField(max_length=100)
    common_name = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.latin_name

    class Meta():     
        db_table = 'species'


class ProteinAlias(models.Model):
    protein = models.ForeignKey('Protein')
    name = models.CharField(max_length=200)
    position = models.SmallIntegerField()

    def __str__(self):
        return self.name

    class Meta():
        ordering = ('position', )
        db_table = 'protein_alias'


class ProteinSet(models.Model):
    protein = models.ManyToManyField('Protein')
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

    class Meta():
        db_table = 'protein_set'


class ProteinSegment(models.Model):
    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=50)
    category = models.CharField(max_length=50)
    position = models.SmallIntegerField()

    def __str__(self):
        return self.name

    class Meta():
        ordering = ('position', )
        db_table = 'protein_segment'


class ProteinSource(models.Model):
    name = models.CharField(max_length=20)

    def __str__(self):
        return self.name

    class Meta():
        db_table = 'protein_source'


class ProteinFamily(models.Model):
    parent = models.ForeignKey('self', null=True)
    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name

    class Meta():
        db_table = 'protein_family'


class ProteinSequenceType(models.Model):
    slug = models.SlugField(max_length=20, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    class Meta():
        db_table = 'protein_sequence_type'